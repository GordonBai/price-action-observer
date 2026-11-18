# Brooks Price Action：公开资料审核与量化范围
核查日期：2026-11-18。此文件是研究索引与工程建议，不是完整课程摘要，也不证明策略有效。

## 访问状态口径
- 已读片段：实际返回文字，可能仅为搜索引擎抓取片段，并非全文。
- 仅目录：核实标题、主题、时长或入口；没有观看视频。
- 访问失败：直接打开遇到 403；不能声称已阅读全文。
- 本次没有观看任何视频，没有获取付费课程或完整教材，没有下载未经授权的镜像。

## 官方来源索引
|编号|资料|状态|用途|
|---|---|---|---|
|S1|[官方术语表](https://www.brookstradingcourse.com/price-action-trading-terms-glossary/)|已读搜索抓取片段；直接打开403|术语定义核对|
|S2|[Al署名的10种形态文章](https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/)|已读搜索抓取片段|概念关系、形态重叠与变体|
|S3|[正式课程目录](https://www.brookstradingcourse.com/trade-price-action/)|仅目录片段；直接打开403|覆盖地图，不等于课程已学习|
|S4|[免费样片](https://www.brookstradingcourse.com/free-sample-price-action-trading-videos/)|已读介绍；视频未观看；直接打开403|12A Market Cycle完整视频入口，20A/B MM样片、37 How to Trade样片、42A失败突破样片、2017 Trading the Open公开演讲|
|S5|[直播室公开样本](https://www.brookstradingcourse.com/online-day-trading-room/)|仅节目说明；视频未观看；直接打开403|2024年11月及2023年11月公开样本；需区分Al与其他讲师|
|S6|[Entering Late in Trends webinar](https://www.brookstradingcourse.com/webinars-lectures/money-show-entering-late-in-trends/)|已读页面介绍和作者评论片段；视频未观看|2015年演讲录像与PDF入口|
|S7|[Opening Breakouts and Reversals webinar](https://www.brookstradingcourse.com/es/webinars-lectures/futures-io-webinar-trading-opening-breakouts-reversals/)|仅介绍、目录片段；视频未观看|2017年开盘突破/反转、前日高低点与开盘区间|
|S8|[Patterns on the Open 官方PDF](https://www.brookstradingcourse.com/wp-content/uploads/2018/10/181030-futuresio-Patterns-on-the-Open-Al-Brooks.pdf)|搜索索引可见，直接打开403|待查阅|
|S9|[Strong Legs TR vs Trends 官方PDF](https://www.brookstradingcourse.com/wp-content/uploads/2016/05/Al-Brooks-Webinar-Distinguishing-Strong-Legs-TR-vs-Trends-May-3-2016.pdf)|搜索索引可见，直接打开403|待查阅|
|S10|[Wiley 官方书籍节选](https://catalogimages.wiley.com/images/db/pdf/9781118066515.excerpt.pdf)|成功打开24页PDF，已读返回的前几页文字；未逐页审图|背景先于形态标签；同一结构可多重解释|
|S11|[Wiley MTR章节摘要](https://onlinelibrary.wiley.com/doi/10.1002/9781119202622.ch3)|已读出版社摘要|趋势、反向突破、测试、第二次反转的顺序|
|S12|[官方论坛目录](https://www.brookstradingcourse.com/support-forum/)|已读目录片段；论坛成员内容不是作者定义|寻找歧义，不作为自动规则权威|

S1的简要要点：inside/outside等局部结构可明确比较OHLC；DB/DT容许近似价位；micro结构是小尺度变体；突破、回踩与失败是随时间演变的事件。S2强调形态变体和重叠，楔形并非必须几何收敛；MM包括等长腿和区间高度投射。S10指出先判断趋势/区间，不宜把命名当交易依据。S11提供MTR的时序结构，但确认仍有主观性。这些只是简要概念索引，不替代原文。

## 研究覆盖地图（不是实现清单）
1. 基础：趋势bar/doji、信号bar/入场bar、inside/outside、ii/iii/ioi/oio、影线与压力。
2. 背景：市场周期、always-in、趋势/区间、spike/channel、tight/broad/micro channel。
3. 水平：前日与会话高低、摆动高低、支撑阻力、磁吸位、开盘缺口、measuring gap。
4. 延续：H1/H2及L1/L2、双底牛旗/双顶熊旗、突破后回踩、微通道首回调。
5. 反转：双底/顶、楔形与三推、MTR、final flag、高潮后反转、失败突破。
6. 其他目录主题：三角、扩张三角、头肩、圆弧、开盘/中段/尾盘陷阱。
7. 目标与管理：等长腿、区间MM、结构失效、风险收益与退出。它们不是单独的方向信号。
8. 延后：rounded、final flag、always-in等需要充分语境，首先输出“候选/启发式”，不能伪装为精确专家判定。

## 原创工程规格建议
下列阈值、状态机与验证规则是本项目提案，不是Brooks官方算法。
- 双底/顶：采用已确认摆动点、ATR或tick容差、最低间隔与中间反弹幅度；分别记录第二次测试候选、反转bar、颈线突破。双底候选不必等待颈线，但不得称为确认突破。
- H1/H2：用明确的回调episode状态机计数，重置规则固定；连续创新高不是多个H计数。记录信号bar和实际越过其极值的trigger bar，禁止回填。
- 三推：用交替摆动和方向性筛选，不强制第三推超过第二推；同时给出更严格的收敛版本，标记两者差异。
- MM：目标必须携带锚点与公式：AB=CD用C+(B-A)；区间突破用上沿+高度或下沿-高度。锚点在确认后冻结、修订另发事件；目标不是必达承诺。
- 区间突破：先冻结旧区间边界，后检测越界；再分别发follow-through、回踩、失败事件，不能用突破bar更新边界后再判断自身。
- MTR：仅输出候选状态链，需有前趋势、反向结构破坏、测试原趋势极值、第二次反转；不可仅凭两个点宣称大反转。
- 解读：事实证据、支持/反对语境、触发位、失效位、目标锚点、缺失信息；评分不是胜率，规则越多不等于独立证据越多。

## 无未来函数与验证要求
- 每条事件保存 event_time、observed_at、confirmed_at、bar_closed、source/feed、规则版本和锚点。
- 右侧k根确认的pivot最早在k根后发布；图可画回原点，交易日志不能。
- 高周期只用已收盘bar；未收盘信号必须标临时并允许撤回。
- 前日/日内session使用交易所时区、假日、夏令时和RTH/ETH配置。
- 前缀一致性测试：全历史前N根的事件必须与仅输入前N根一致。
- 乱序、重复、修订、断流、零range、跨日与拆股都要测试。
- K线无法确定同bar内先止损还是先止盈；标歧义或保守处理，不优化成盈利。
- 首先做事件审计和标注一致性，再做含费用滑点、跨天样本外评估；不凭一天SOXL验证准确率。

## 后续研究顺序
A. 先补齐S1/S2全文和S4公开MM/市场周期样片，逐条记页码/时间戳及未解问题。
B. 从S5公开直播做逐bar“当时可知”标注，与事后图解分开。
C. 同一形态收集正例、失败例、相似但不满足例，不只搜成功案例。
D. 对S3建立章节→概念→证据→规则→测试映射；目录未知部分保留待研究。
E. 不因免费可看就默认可再分发；项目保存索引、原创规则和少量必要引文，不拷贝完整课程/视频/书籍。
