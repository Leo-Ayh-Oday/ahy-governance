# 贡献指南

感谢你愿意为 Ahy Governance 贡献代码。这份指南覆盖了从环境搭建到 PR 提交的全流程。

## 目录

- [开发环境搭建](#开发环境搭建)
- [提交规范](#提交规范)
- [PR 工作流](#pr-工作流)
- [代码风格](#代码风格)
- [测试要求](#测试要求)
- [文档规范](#文档规范)

## 开发环境搭建

```bash
# 克隆项目
git clone https://github.com/Leo-Ayh-Oday/ahy-governance.git
cd ahy-governance

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS/Linux

# 安装开发依赖
pip install -e ".[web,postgres,redis,security,crewai,mcp,observability]"
pip install pytest pytest-cov ruff bandit
```

启动 Dashboard 验证环境：

```bash
ahy-dashboard
# 浏览器打开 http://localhost:8081
```

## 提交规范

遵循 [约定式提交](https://www.conventionalcommits.org/zh-hans/)：

```
<类型>: <描述>

feat: 新增冲突自动解决功能
fix: 修复多模型成本归因错误
docs: 更新 MCP 集成文档
test: 补充自愈模块测试覆盖
refactor: 提取审计哈希链公共逻辑
chore: 升级 fastmcp 到 3.x
```

类型：`feat`（新功能）、`fix`（修复）、`docs`（文档）、`test`（测试）、`refactor`（重构）、`chore`（杂项）、`perf`（性能）、`ci`（流水线）

## PR 工作流

1. **Fork 并创建分支** — 从 `main` 拉一个功能分支
2. **编码实现** — 遵循代码风格、写好测试
3. **自查** — 对照下方清单逐项检查
4. **跑测试** — `pytest tests/ -v --cov=ahy_governance --cov-report=term`
5. **提交 PR** — 填写 PR 模板、关联相关 Issue
6. **CI 全部通过** — 测试、lint、安全扫描、覆盖率门槛（80%+）

### PR 自检清单

- [ ] 新功能有对应测试
- [ ] 已有测试全部通过（`pytest tests/`）
- [ ] Ruff 检查通过（`ruff check .`）
- [ ] 测试覆盖率不低于 80%
- [ ] 无硬编码密钥或凭据
- [ ] 涉及变更的文档已更新
- [ ] 提交信息遵循约定式提交格式

## 代码风格

我们使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查和格式化。配置见 `pyproject.toml`：

- Python 版本：3.10+
- 行长度：100
- 检查规则：E, F, W, I, N, UP, B, SIM

```bash
ruff check .       # 检查代码
ruff check --fix . # 自动修复
```

### 风格指南

- **函数**：尽量控制在 50 行以内
- **文件**：尽量控制在 800 行以内，超出时拆分模块
- **不可变性**：优先返回新对象，而不是直接修改原对象
- **类型注解**：公开 API 必须标注，内部辅助函数可选
- **文档字符串**：公开模块、类和函数必须写
- **提前返回**：优先用提前返回来减少嵌套层级

## 测试要求

```bash
# 跑全部测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ -v --cov=ahy_governance --cov-report=term --cov-report=html

# 只跑某一个测试文件
pytest tests/test_conflict_detector.py -v

# 安全扫描
bandit -r ahy_governance/ -ll
```

### 测试结构

```
tests/
├── test_conflict_detector.py   # 冲突检测
├── test_cost_tracker.py        # 成本追踪
├── test_audit_reporter.py      # 审计报告
├── test_health_monitor.py      # 健康监控
├── test_auth_rbac.py           # 权限管理
├── test_self_healer.py         # 自愈模块
├── test_mcp_server.py          # MCP 服务
└── ...
```

测试使用 AAA 模式（准备 → 执行 → 断言），测试名称要说清楚测了什么。

```python
def test_冲突检测器能发现两个Agent的作用域不匹配():
    # 准备
    detector = ConflictDetector()
    输出1 = {"scope": "read_only"}
    输出2 = {"scope": "write"}

    # 执行
    conflicts = detector.check(输出1, 输出2)

    # 断言
    assert len(conflicts) == 1
    assert conflicts[0].type == "scope"
```

## 文档规范

- **用户文档**：更新 `README.md`、`README_CN.md` 和 `docs/` 目录
- **API 文档**：公开函数的 docstring，Google 风格
- **更新日志**：在 `CHANGELOG.md` 的 `[Unreleased]` 下添加条目

## 遇到问题

- **讨论**：[GitHub Discussions](https://github.com/Leo-Ayh-Oday/ahy-governance/discussions)
- **Bug**：[GitHub Issues](https://github.com/Leo-Ayh-Oday/ahy-governance/issues)
- **安全漏洞**：见 [SECURITY_CN.md](SECURITY_CN.md)
