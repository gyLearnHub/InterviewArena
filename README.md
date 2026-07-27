<p align="center">
  <img src=".github/assets/readme-hero.webp" width="100%" alt="一名候选人在 InterviewArena 中接受四位 AI 面试官的多轮模拟面试" />
</p>

<h1 align="center">InterviewArena</h1>

<p align="center">
  <strong>多 Agent 协作、长短期记忆与可观测 Harness 驱动的 AI 面试训练系统</strong>
</p>

<p align="center">
  不止完成一次模拟面试，而是让每轮表现成为下一次训练的上下文、证据与改进起点。
</p>

<p align="center">
  <a href="https://github.com/gyLearnHub/InterviewArena/actions/workflows/quality.yml"><img src="https://img.shields.io/github/actions/workflow/status/gyLearnHub/InterviewArena/quality.yml?branch=master&label=quality&style=flat-square" alt="Quality workflow" /></a>
  <a href="https://github.com/gyLearnHub/InterviewArena/actions/workflows/e2e.yml"><img src="https://img.shields.io/github/actions/workflow/status/gyLearnHub/InterviewArena/e2e.yml?label=e2e&style=flat-square" alt="E2E workflow" /></a>
</p>

<p align="center">
  <a href="#核心优势">核心优势</a> ·
  <a href="#长短期记忆">长短期记忆</a> ·
  <a href="#训练闭环">训练闭环</a> ·
  <a href="#隐私安全与可靠性">隐私、安全与可靠性</a> ·
  <a href="#产品预览">产品预览</a> ·
  <a href="#系统架构">系统架构</a> ·
  <a href="#持续集成ci">持续集成</a>
</p>

## 核心优势

InterviewArena 的重点不是“接入一个模型然后连续出题”，而是把面试训练拆成可编排、可记忆、可评估、可恢复的完整 Agent 系统。

<table>
  <tr>
    <td width="33%" valign="top">
      <strong>🤝 多 Agent 分工编排</strong><br /><br />
      简历、技术、主管、HR 四类面试官拥有独立提示词、关注维度和结束策略；评估 Agent 与 Skill Runner 参与逐题、逐轮和最终总结，由统一编排器传递上下文。
    </td>
    <td width="33%" valign="top">
      <strong>🧠 分层的长短期记忆</strong><br /><br />
      短期记忆在单场面试中保留最近问答、滚动摘要和已完成轮次；长期记忆沉淀跨场表现与 Agent 经验。两层记忆分别控制时效和检索范围，再共同进入面试上下文。
    </td>
    <td width="33%" valign="top">
      <strong>🛡️ Agent Harness</strong><br /><br />
      Trace、规则校验、结构化输出验证、自动重试、降级和 Checkpoint 贯穿长流程；独立诊断页展示规则通过率、失败节点、重试记录与可恢复状态。
    </td>
  </tr>
  <tr>
    <td width="33%" valign="top">
      <strong>📐 证据化多级评估</strong><br /><br />
      单题评价、轮次总结和综合报告三级汇总，保留维度得分、优缺点、建议与证据；报告额外展示评分覆盖率、得分来源和可信度状态。
    </td>
    <td width="33%" valign="top">
      <strong>🔁 可持续训练闭环</strong><br /><br />
      从逐题反馈或最终报告生成复盘收藏，追踪薄弱项练习进度；新的面试再次读取历史记忆，让训练从“重复做题”变成持续修正。
    </td>
    <td width="33%" valign="top">
      <strong>🧪 面试策略自动优化</strong><br /><br />
      系统从历史面试中学习，持续迭代面试官提示词、提问流程和质量规则，让提问针对性、岗位适配度和输出稳定性随训练积累逐步提升。每次迭代都需通过真实与合成样本验证，效果下降时自动回滚。
    </td>
  </tr>
</table>

## 长短期记忆

两层记忆解决的问题不同：短期记忆保证当前面试能够接着聊，长期记忆让下一场训练不必从零开始。系统不会把所有历史记录直接塞进 Prompt，而是按生命周期和使用场景控制上下文。

| 记忆层   | 主要内容                                                                 | 作用                                                   |
| -------- | ------------------------------------------------------------------------ | ------------------------------------------------------ |
| 短期记忆 | 最近问答、滚动摘要、已完成轮次、待追问方向和一致性标记                   | 跨轮承接回答，减少重复提问，及时发现前后矛盾           |
| 长期记忆 | 候选人的优势、薄弱项和表达偏好，以及面试官经验、Agent 经验和训练复盘结果 | 跨场个性化提问，持续追踪能力变化，复用已经验证过的经验 |

生成问题时，系统会结合当前面试的短期上下文和与本轮相关的长期记忆。这样既能接住刚才的回答，也能利用过去训练中已经确认的优势和薄弱项。

## 训练闭环

<p align="center">
  <img src=".github/assets/readme-training-flow.png" width="100%" alt="InterviewArena 从简历解析、岗位策略、短期上下文、多 Agent 面试、证据化评估、长期记忆到专项复盘的训练闭环，Harness 贯穿全流程" />
</p>

系统在单场面试中持续更新短期上下文，结束后再把评估结果沉淀为长期记忆和复盘任务，供下一次训练使用。

## 隐私、安全与可靠性

InterviewArena 会处理简历、岗位描述和面试记录，因此模型调用边界与个人数据生命周期也是系统能力的一部分：

- **模型数据边界**：只有用户明确授权后，系统才会把脱敏后的简历、岗位描述和面试内容发送给第三方模型服务；授权可以在设置中撤回。
- **个人数据控制**：设置页支持导出账户数据副本、清除长期记忆和注销账户；删除简历或历史记录时会同步处理相关引用，避免残留可识别内容。
- **可靠执行与排障**：登录和注册接口包含限流保护，后台任务使用持久化状态、租约、幂等键和重试机制；就绪检查、请求编号和指标接口用于发现数据库、存储与任务运行器异常。

具体的数据保留规则、部署约束和生产检查项见[模型数据与个人数据生命周期](docs/configuration-and-deployment.md#模型数据与个人数据生命周期)。

## 产品预览

<table>
  <tr>
    <td width="50%" align="center">
      <img src=".github/assets/readme-dashboard.webp" alt="InterviewArena 工作台，展示综合表现、四轮能力、薄弱项和复盘收藏" />
      <br />
      <strong>训练工作台</strong><br />综合表现、四轮能力、薄弱项与复盘任务集中呈现
    </td>
    <td width="50%" align="center">
      <img src=".github/assets/readme-interview.webp" alt="InterviewArena 技术面界面，展示多轮进度、问答和即时评分" />
      <br />
      <strong>多轮模拟面试</strong><br />面试进度、上下文问答、逐题评分和追问方向同步更新
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <img src=".github/assets/readme-report.webp" alt="InterviewArena 面试复盘报告，展示综合评分和报告可信度" />
      <br />
      <strong>证据化面试复盘</strong><br />综合结论、四轮得分、评分覆盖率和得分来源清晰可查
    </td>
    <td width="50%" align="center">
      <img src=".github/assets/readme-memories.webp" alt="InterviewArena 长期记忆页面，展示薄弱项、优势和回答偏好" />
      <br />
      <strong>长期记忆管理</strong><br />沉淀薄弱项、优势与表达偏好，支持后续个性化训练
    </td>
  </tr>
</table>

> 截图来自当前 Vue 前端的实际页面；其中账户、岗位、评分等数据为演示数据。

## 系统架构

<p align="center">
  <img src=".github/assets/readme-architecture.png" width="100%" alt="InterviewArena 分层系统架构：Vue 3、FastAPI、面试编排器、四类 Agent、评估、技能、Memory RAG、Harness、安全进化以及数据与模型基础设施" />
</p>

## 持续集成（CI）

CI 是 **Continuous Integration（持续集成）** 的缩写。README 顶部的徽章显示 GitHub Actions 自动检查的最近结果：

| 徽章      | 覆盖范围                                                                                                              | 状态来源                                        |
| --------- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| `quality` | 生成的 API 契约一致性、后端 Ruff/Mypy/Pytest，以及前端 ESLint/Prettier、类型检查和生产构建                            | `master` 分支最近一次 Quality 工作流            |
| `e2e`     | Playwright 前端端到端测试，以及连接真实 FastAPI、MySQL 和 Redis 的全栈 smoke 测试，覆盖就绪检查、注册登录和工作台加载 | 最近一次由 Pull Request 或手动触发的 E2E 工作流 |

绿色 `passing` 表示对应工作流最近一次运行全部通过；红色 `failing` 表示至少有一项检查失败。点击徽章可以查看运行记录和失败日志。徽章通过不代表项目绝对没有缺陷，但说明当前代码已经通过仓库定义的自动化质量门槛。

## 从一次真实练习开始

如果你正在准备技术面试，可以按照 [快速开始](docs/configuration-and-deployment.md#快速开始) 跑完一场多轮练习。用过之后，欢迎把不自然的提问、评分偏差或缺失的面试场景提交到 [Issues](https://github.com/gyLearnHub/InterviewArena/issues)。真实使用中发现的问题，最能帮助项目继续改进。

觉得 InterviewArena 有用，可以点一个 Star，或者把它分享给同样在准备面试的人。想直接参与开发，也欢迎提交 Pull Request。

## 使用、配置与部署

技术栈、快速开始、环境变量、Cookie 与 CSRF、跨域访问、数据库升级、健康检查、质量保障和生产发布要求统一放在独立文档站中：

👉 [打开 InterviewArena 使用、配置与部署指南](https://gylearnhub.github.io/InterviewArena/)

如果文档站暂时不可用，也可以查看[仓库内 Markdown 版本](docs/configuration-and-deployment.md)。
