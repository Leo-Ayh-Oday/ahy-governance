"""
Conflict Detector — 跨 Agent 输出冲突检测引擎

检测类型（规则引擎）:
  FACT_CONFLICT       — 两个 Agent 对同一实体给出矛盾事实
  FORMAT_MISMATCH     — 上游输出格式与下游期望不匹配
  DEPENDENCY_BREAK    — 下游依赖的字段在上游输出中缺失
  SCOPE_OVERLAP       — 两个 Agent 产出了重复/重叠内容
  CONFIDENCE_CLASH    — Agent A 高置信度的结论与 Agent B 警告冲突
  SEMANTIC_CONFLICT   — LLM 语义级矛盾检测（异步，source="semantic"）

严重程度: CRITICAL > HIGH > MEDIUM > LOW

用法:
  detector = ConflictDetector()
  conflicts = detector.check(
      step_outputs=pipeline.step_outputs,
      dag=WORKFLOW_DAG.get(workflow_name, {}),
  )
  for c in conflicts:
      if c.severity == "CRITICAL":
          yield {"type": "conflict_alert", "conflict": c.to_dict()}
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ConflictType(Enum):
    FACT_CONFLICT = "fact_conflict"
    FORMAT_MISMATCH = "format_mismatch"
    DEPENDENCY_BREAK = "dependency_break"
    SCOPE_OVERLAP = "scope_overlap"
    CONFIDENCE_CLASH = "confidence_clash"
    SEMANTIC_CONFLICT = "semantic_conflict"


class Severity(Enum):
    CRITICAL = "CRITICAL"   # 阻塞流水线
    HIGH = "HIGH"           # 继续但强制标记
    MEDIUM = "MEDIUM"       # 人工复核建议
    LOW = "LOW"             # 仅供参考


@dataclass
class Conflict:
    """一次冲突检测结果"""
    conflict_type: ConflictType
    severity: Severity
    agents_involved: list[str]
    description: str
    evidence: dict = field(default_factory=dict)  # {agent_name: excerpt}
    suggestion: str = ""
    source: str = "rule"  # "rule" | "semantic" — for auditability

    def to_dict(self) -> dict:
        return {
            "type": self.conflict_type.value,
            "severity": self.severity.value,
            "agents": self.agents_involved,
            "description": self.description,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
            "source": self.source,
        }

    def to_sse(self) -> dict:
        """作为 SSE event 发送给前端"""
        return {"type": "conflict_alert", "conflict": self.to_dict()}


# ── 事实词典：常见实体 + 属性，用于跨 Agent 事实一致性比对 ──────────

# 每个条目: (entity_pattern, [attribute_names])
# 我们从 Agent 输出中提取 <实体, 属性> 对，比对是否一致
FACT_PATTERNS = [
    # 日期/时间
    (r"(?:截止日期|交付日期|deadline|due\s*date)[:\s]*(\S+)", "deadline"),
    (r"(?:合同期限|有效期|contract\s*term)[:\s]*(\S+)", "contract_term"),
    # 金额/费用
    (r"(?:合同金额|总价|金额|amount|total|price)[:\s]*([\d,.]+\s*(?:万元|元|USD|RMB|万|亿)?)", "amount"),
    (r"(?:违约金|罚金|penalty|damages)[:\s]*([\d,.]+\s*(?:万元|元|USD|RMB|万|亿)?)", "penalty"),
    (r"(?:利率|费率|rate)[:\s]*([\d,.]+%)", "rate"),
    # 人员/主体
    (r"(?:甲方|Party\s*A|雇主|Employer)[:\s]*(\S+)", "party_a"),
    (r"(?:乙方|Party\s*B|雇员|Employee)[:\s]*(\S+)", "party_b"),
    # 风险等级
    (r"(?:风险等级|风险|risk\s*level)[:\s]*(\S+)", "risk_level"),
    (r"(?:合规状态|compliance)[:\s]*(\S+)", "compliance"),
    # 数量
    (r"(?:数量|库存|quantity|stock)[:\s]*(\d+)", "quantity"),
    (r"(?:件数|批次|batch|lot)[:\s]*(\d+)", "batch_count"),
]


@dataclass
class ConflictDetector:
    """跨 Agent 冲突检测器。

    在编排器每个 step 完成后调用 check()，传入当前所有 step_outputs。
    返回冲突列表 — 为空表示无冲突。

    语义模式: enable_semantic=True 时，规则引擎结果立即返回，
    语义检测异步运行，结果通过 semantic_results 属性追加。
    """

    fact_patterns: list[tuple] = field(default_factory=lambda: FACT_PATTERNS)
    strict_mode: bool = False
    enable_semantic: bool = False
    semantic_detector: object | None = None

    def check(
        self,
        step_outputs: dict,  # {step_id: AgentResult}
        dag: dict = None,     # {"steps": [...], "edges": [...]}
    ) -> list[Conflict]:
        """对所有已完成的 Agent 步骤做交叉冲突检测。

        Args:
            step_outputs: {step_id: AgentResult} — 流水线到目前为止的产出
            dag: 工作流 DAG 定义，含 edges（依赖关系）

        Returns:
            Conflict 列表。空列表 = 无冲突。
        """
        conflicts = []
        results = {}
        for sid, r in step_outputs.items():
            out = r.output
            if isinstance(out, dict) and "_raw" in out and len(out) == 1:
                results[sid] = out["_raw"]  # 纯文本输出，展开为字符串
            else:
                results[sid] = out if isinstance(out, dict) else {"_raw": str(out)}

        # 至少需要 2 个 Agent 产出才能做冲突检测
        if len(results) < 2:
            return conflicts

        # 1. 事实冲突检测
        conflicts.extend(self._detect_fact_conflicts(results))

        # 2. 依赖断链检测
        if dag:
            conflicts.extend(self._detect_dependency_breaks(results, dag))

        # 3. 输出格式不匹配检测
        conflicts.extend(self._detect_format_mismatches(results, dag or {}))

        # 4. 范围重叠检测
        conflicts.extend(self._detect_scope_overlaps(results))

        # 5. 置信度冲突检测
        conflicts.extend(self._detect_confidence_clashes(results))

        # 6. 语义冲突检测（异步，结果标记 source="semantic"）
        if self.enable_semantic and self.semantic_detector:
            try:
                semantic_results = self.semantic_detector.detect_batch(
                    {k: str(v) for k, v in results.items()},
                    existing_conflicts=conflicts,
                )
                for sr in semantic_results:
                    sev = {"HIGH": Severity.HIGH, "MEDIUM": Severity.MEDIUM,
                           "LOW": Severity.LOW}.get(sr.severity, Severity.MEDIUM)
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.SEMANTIC_CONFLICT,
                        severity=sev,
                        agents_involved=sr.agents_involved,
                        description=sr.description,
                        evidence={a: "" for a in sr.agents_involved},
                        suggestion=sr.suggestion,
                        source="semantic",
                    ))
            except Exception:
                pass  # 语义检测失败不影响规则引擎结果

        return conflicts

    # ── 事实冲突 ─────────────────────────────────────────────────

    def _detect_fact_conflicts(self, results: dict) -> list[Conflict]:
        """检测两个 Agent 对同一实体是否给出矛盾值。"""
        conflicts = []
        agent_facts: dict[str, dict[str, str]] = {}

        for agent_name, output in results.items():
            # 直接读取 dict 字段，不依赖正则
            facts = {}
            if isinstance(output, dict):
                facts = self._extract_facts_from_dict(output)
            else:
                # 非 dict → 用正则从文本提取
                text = str(output)
                facts = self._extract_facts_from_text(text)
            if facts:
                agent_facts[agent_name] = facts

        # 比对：同一属性在不同 Agent 中的值
        agent_names = list(agent_facts.keys())
        for i in range(len(agent_names)):
            for j in range(i + 1, len(agent_names)):
                a1, a2 = agent_names[i], agent_names[j]
                common_attrs = set(agent_facts[a1].keys()) & set(agent_facts[a2].keys())
                for attr in common_attrs:
                    v1, v2 = agent_facts[a1][attr], agent_facts[a2][attr]
                    if v1 != v2:
                        # 数字类属性允许小差异
                        if self._numeric_close(v1, v2):
                            continue
                        conflicts.append(Conflict(
                            conflict_type=ConflictType.FACT_CONFLICT,
                            severity=Severity.HIGH,
                            agents_involved=[a1, a2],
                            description=f"属性 '{attr}' 值矛盾: {a1}={v1}, {a2}={v2}",
                            evidence={a1: v1, a2: v2},
                            suggestion=f"人工确认 '{attr}' 的正确值，统一后重新运行"
                        ))
        return conflicts

    # ── 依赖断链 ─────────────────────────────────────────────────

    def _detect_dependency_breaks(self, results: dict, dag: dict) -> list[Conflict]:
        """检测下游 Agent 依赖的字段在上游输出中缺失。"""
        conflicts = []
        edges = dag.get("edges", [])
        steps = {s["id"]: s for s in dag.get("steps", [])}

        for edge in edges:
            upstream_id = edge.get("from")
            downstream_id = edge.get("to")
            if upstream_id not in results or downstream_id not in results:
                continue

            upstream_output = results[upstream_id]
            if not isinstance(upstream_output, dict):
                continue

            # 检查下游期望的字段是否在上游输出中存在
            downstream_step = steps.get(downstream_id, {})
            expected_fields = self._infer_expected_fields(downstream_step, upstream_step=steps.get(upstream_id, {}))

            missing = []
            for field in expected_fields:
                if field not in upstream_output or upstream_output[field] is None:
                    missing.append(field)

            if missing:
                conflicts.append(Conflict(
                    conflict_type=ConflictType.DEPENDENCY_BREAK,
                    severity=Severity.CRITICAL,
                    agents_involved=[upstream_id, downstream_id],
                    description=f"{downstream_id} 依赖 {upstream_id} 的字段 [{', '.join(missing)}]，但上游未产出",
                    evidence={"missing_fields": missing, "upstream_output_keys": list(upstream_output.keys())},
                    suggestion=f"检查 {upstream_id} 的 output_schema 是否包含 {', '.join(missing)}"
                ))
        return conflicts

    # ── 格式不匹配 ───────────────────────────────────────────────

    def _detect_format_mismatches(self, results: dict, dag: dict) -> list[Conflict]:
        """检测下游期望的 JSON 类型与实际产出类型不一致。"""
        conflicts = []
        edges = dag.get("edges", [])
        steps = {s["id"]: s for s in dag.get("steps", [])}

        for edge in edges:
            up_id = edge.get("from")
            down_id = edge.get("to")
            if up_id not in results or down_id not in results:
                continue

            up = results[up_id]
            if not isinstance(up, dict):
                continue

            # 从下游 AgentConfig 的 output_schema 推断期望类型
            down_step = steps.get(down_id, {})
            expected_schema = down_step.get("output_schema", {})
            if not expected_schema:
                continue

            for field, spec in expected_schema.get("properties", {}).items():
                expected_type = spec.get("type", "string")
                if field in up:
                    actual = up[field]
                    if not self._type_matches(actual, expected_type):
                        conflicts.append(Conflict(
                            conflict_type=ConflictType.FORMAT_MISMATCH,
                            severity=Severity.HIGH,
                            agents_involved=[up_id, down_id],
                            description=f"字段 '{field}': {up_id} 产出类型 {type(actual).__name__}，{down_id} 期望 {expected_type}",
                            evidence={"field": field, "expected": expected_type, "actual": type(actual).__name__},
                            suggestion=f"修改 {up_id} 的 output_schema 使 '{field}' 类型为 {expected_type}"
                        ))
        return conflicts

    # ── 范围重叠 ─────────────────────────────────────────────────

    def _detect_scope_overlaps(self, results: dict) -> list[Conflict]:
        """检测两个 Agent 产出了高度重叠的内容（浪费）。"""
        conflicts = []
        agent_names = list(results.keys())
        for i in range(len(agent_names)):
            for j in range(i + 1, len(agent_names)):
                a1, a2 = agent_names[i], agent_names[j]
                t1 = json.dumps(results[a1], ensure_ascii=False) if isinstance(results[a1], dict) else str(results[a1])
                t2 = json.dumps(results[a2], ensure_ascii=False) if isinstance(results[a2], dict) else str(results[a2])

                similarity = self._jaccard_similarity(t1, t2)
                if similarity > 0.6:
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.SCOPE_OVERLAP,
                        severity=Severity.MEDIUM,
                        agents_involved=[a1, a2],
                        description=f"{a1} 和 {a2} 产出高度重叠 (相似度 {similarity:.0%})，可能存在重复工作",
                        evidence={"similarity": round(similarity, 2)},
                        suggestion=f"检查 {a1} 和 {a2} 的职责划分是否清晰，考虑合并或重新分配"
                    ))
        return conflicts

    # ── 置信度冲突 ───────────────────────────────────────────────

    def _detect_confidence_clashes(self, results: dict) -> list[Conflict]:
        """检测 Agent A 高置信度的结论与 Agent B 的警告/不确定性冲突。"""
        conflicts = []
        agent_names = list(results.keys())

        for i in range(len(agent_names)):
            for j in range(i + 1, len(agent_names)):
                a1, a2 = agent_names[i], agent_names[j]
                o1 = results[a1]
                o2 = results[a2]

                # 检查是否有 confidence / risk_level 字段冲突
                conf1 = self._extract_confidence(o1)
                conf2 = self._extract_confidence(o2)

                if conf1 is not None and conf2 is not None:
                    # 高置信 vs 低置信冲突
                    if (conf1 >= 0.8 and conf2 <= 0.3) or (conf2 >= 0.8 and conf1 <= 0.3):
                        high_agent = a1 if conf1 >= 0.8 else a2
                        low_agent = a2 if conf1 >= 0.8 else a1
                        conflicts.append(Conflict(
                            conflict_type=ConflictType.CONFIDENCE_CLASH,
                            severity=Severity.HIGH,
                            agents_involved=[a1, a2],
                            description=f"{high_agent} 高置信度 ({max(conf1, conf2):.0%})，但 {low_agent} 低置信度 ({min(conf1, conf2):.0%})",
                            evidence={a1: conf1, a2: conf2},
                            suggestion=f"人工复核 {low_agent} 的低置信度判断，确认是否需要重新执行"
                        ))

                # 检查 risk_level 冲突
                risk1 = self._extract_risk(o1)
                risk2 = self._extract_risk(o2)
                risk_levels = {"低": 0, "low": 0, "中": 1, "medium": 1, "高": 2, "high": 2, "严重": 3, "critical": 3}
                if risk1 in risk_levels and risk2 in risk_levels:
                    diff = abs(risk_levels[risk1] - risk_levels[risk2])
                    if diff >= 2:
                        conflicts.append(Conflict(
                            conflict_type=ConflictType.CONFIDENCE_CLASH,
                            severity=Severity.CRITICAL,
                            agents_involved=[a1, a2],
                            description=f"{a1} 风险评估={risk1}, {a2} 风险评估={risk2}，相差 {diff} 级",
                            evidence={a1: risk1, a2: risk2},
                            suggestion=f"立即人工复核，两个 Agent 的风险判断严重不一致"
                        ))
        return conflicts

    # ── 事实提取 ─────────────────────────────────────────────────

    @staticmethod
    def _extract_facts_from_dict(output: dict) -> dict[str, str]:
        """从 dict 输出中直接提取事实字段。"""
        # 如果有 _raw 字段，用文本提取
        if "_raw" in output and len(output) == 1:
            return ConflictDetector._extract_facts_from_text(str(output["_raw"]))

        facts = {}
        field_map = {
            "deadline": ["deadline", "due_date", "截止日期", "交付日期", "截止时间"],
            "contract_term": ["contract_term", "有效期", "合同期限", "term"],
            "amount": ["amount", "总价", "金额", "total", "price", "合同金额"],
            "penalty": ["penalty", "违约金", "罚金", "damages"],
            "rate": ["rate", "利率", "费率", "interest_rate"],
            "party_a": ["party_a", "甲方", "employer", "雇主", "委托方"],
            "party_b": ["party_b", "乙方", "employee", "雇员", "受托方"],
            "risk_level": ["risk_level", "风险等级", "风险", "risk"],
            "compliance": ["compliance", "合规状态", "合规"],
            "quantity": ["quantity", "数量", "库存", "stock", "qty"],
            "batch_count": ["batch_count", "批次", "batch", "lot", "件数"],
        }
        for attr, keys in field_map.items():
            for k in keys:
                if k in output and output[k] is not None:
                    v = output[k]
                    if isinstance(v, (int, float)):
                        facts[attr] = str(v)
                    else:
                        facts[attr] = str(v).strip().lower().strip("\"'")
                    break
        return facts

    @staticmethod
    def _extract_facts_from_text(text: str) -> dict[str, str]:
        """从纯文本中正则提取事实字段。"""
        facts = {}
        for pattern, attr_name in FACT_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                val = matches[0].strip().lower().strip("\"'")
                facts[attr_name] = val
        return facts

    # ── 辅助方法 ─────────────────────────────────────────────────

    @staticmethod
    def _numeric_close(v1: str, v2: str) -> bool:
        """判断两个数字字符串是否在 5% 误差内相等。"""
        try:
            n1 = float(v1.replace(",", "").replace("万元", "0000").replace("元", "").replace("USD", "").replace("RMB", "").strip())
            n2 = float(v2.replace(",", "").replace("万元", "0000").replace("元", "").replace("USD", "").replace("RMB", "").strip())
            if n1 == 0 and n2 == 0:
                return True
            return abs(n1 - n2) / max(abs(n1), abs(n2)) < 0.05
        except ValueError:
            return False

    @staticmethod
    def _type_matches(value, expected_type: str) -> bool:
        type_map = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "array": list, "object": dict}
        return isinstance(value, type_map.get(expected_type, object))

    @staticmethod
    def _infer_expected_fields(step: dict, upstream_step: dict = None) -> list[str]:
        """从 step 的 system_prompt 推断它依赖上游的哪些字段。"""
        prompt = step.get("system_prompt", "") + step.get("description", "")
        # 从 upstream 的 output_schema 获取字段列表
        if upstream_step and upstream_step.get("output_schema"):
            props = upstream_step["output_schema"].get("properties", {})
            required = upstream_step["output_schema"].get("required", list(props.keys()))
            return required
        # 从 prompt 中推断引用的字段
        import re
        refs = re.findall(r'(?:使用|参考|根据|based\s*on|from|using)\s*(?:前置|上游|previous|upstream)?\s*(?:步骤|step)?\s*[的]?\s*[`"\']?(\w+)[`"\']?', prompt, re.IGNORECASE)
        return list(set(refs)) if refs else []

    @staticmethod
    def _extract_confidence(output: dict) -> Optional[float]:
        """从输出中提取置信度数值。"""
        if isinstance(output, dict):
            for key in ("confidence", "confidence_score", "置信度", "score"):
                v = output.get(key)
                if isinstance(v, (int, float)):
                    return float(v)
                if isinstance(v, str):
                    try:
                        return float(v.replace("%", "")) / (100 if "%" in v else 1)
                    except ValueError:
                        pass
        return None

    @staticmethod
    def _extract_risk(output: dict) -> Optional[str]:
        """从输出中提取风险等级字符串。"""
        if isinstance(output, dict):
            for key in ("risk_level", "risk", "风险等级", "风险", "severity"):
                v = output.get(key)
                if isinstance(v, str):
                    return v.strip().lower()
        return None

    @staticmethod
    def _jaccard_similarity(text1: str, text2: str) -> float:
        """Jaccard 相似度 (3-gram)。"""
        def ngrams(s, n=3):
            s = s.lower()
            return {s[i:i+n] for i in range(max(0, len(s) - n + 1))}
        g1, g2 = ngrams(text1), ngrams(text2)
        if not g1 or not g2:
            return 0.0
        return len(g1 & g2) / len(g1 | g2)


# ── 模块级便捷函数 ──────────────────────────────────────────────

_detector: Optional[ConflictDetector] = None


def get_detector(strict: bool = False) -> ConflictDetector:
    global _detector
    if _detector is None:
        _detector = ConflictDetector(strict_mode=strict)
    return _detector


def check_conflicts(
    step_outputs: dict,
    dag: dict = None,
    strict: bool = False,
) -> list[Conflict]:
    """便捷函数：检测冲突。"""
    d = ConflictDetector(strict_mode=strict)
    return d.check(step_outputs, dag)


# ── Module-level utilities ─────────────────────────────────────