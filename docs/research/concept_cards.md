# Brooks 公开文本概念卡与实现合同
日期：2026-11-18。第二轮研究。所有“工程规格”均为原创、待验证的形式化近似，不是作者发布的算法。

## 阅读与证据边界
本轮读取了搜索工具返回的官方原文正文段落，不只是标题或目录。对candlestick、trading ranges、statistics、5 steps四个页面直接打开均403；因此只能说读过返回段落，不能声称网页全文、图像和嵌入视频均已审阅。以下提及的历史案例来自作者文字说明，尚未独立核对图中OHLC。未使用第三方教材镜像。

## C01：context + signal，不是蜡烛形状分类器
**来源**：[Price action and candlestick charts](https://www.brookstradingcourse.com/how-to-trade-manual/candlestick-charts/)，2020-04-23，已读Setups and Signals及其他正文段落。
**概念**：同一蜡烛信号在不同左侧背景下意义不同；文章用紧区间中漂亮形态仍可能表现不佳来说明这一点。
**工程规格**：pattern检测与context分类分层。输出事实形态但在区间中段添加`context_conflict`，不要简单加总成买入分数。
**验收**：复制同一末端三根bar，分别接强趋势和紧区间历史；形态标签可相同，解读和资格状态必须不同。
**未解决**：强弱背景的阈值需项目自定并检验。

## C02：市场周期是状态演变
**来源**：[Trading ranges – areas of confusion](https://www.brookstradingcourse.com/how-to-trade-manual/trading-ranges/)，2020-10-25，已读Market cycles、Most breakout attempts fail等正文段落。
**概念**：作者描述突破、出现回调后的通道、双向交易增长后的区间；紧区间宜谨慎，区间中部缺乏位置优势。一个强单腿不自动证明区间已变趋势。
**工程规格**：状态用`breakout_candidate / trend_channel / range / uncertain`，另有transition证据。边界固定到突破前一根；重叠比例、方向效率、回调幅度、follow-through分别保留。
**验收**：区间顶大阳线但下一根收回，应留下“尝试→失败”事件，不将历史全部改成趋势。
**SOXL适配**：20根等长度阈值不能直接把5分钟教学等同1分钟；同时记录bar_count和elapsed_minutes。

## C03：setup、信号bar、触发与成交不同
**来源**：[Beginners should enter with stop orders](https://www.brookstradingcourse.com/how-to-trade-manual/stop-orders/)，2020-05-17，已读正文。
**概念**：文中区分信号bar与随后入场bar，并以超越前者极值的stop entry解释方向确认；区间中的另一方可能采用相反的交易逻辑。该文的概率数值不应直接当成系统统计。
**工程规格**：`candidate → armed → triggered → invalidated/expired`；trigger_price与stop_price名称明确。没有真实订单时用`theoretical_trigger`，绝不能输出“已成交”。
**验收**：信号bar收盘时只能armed；下一根高点未越过触发价不得triggered。跳空跨过触发价不能假设仍以触发价成交。

## C04：MM是参考水平，不是摸到就反转
**来源**：[Ask Al: Trading range days price action](https://www.brookstradingcourse.com/ask-al/trading-range-days-price-action/)，已读Fading measured move targets原文段落。
**概念**：作者将MM视为与其他支撑阻力类似的水平，强调背景；强熊趋势里仅因到达下行MM就挂买单并不合理。
**工程规格**：MM单独事件`projection_created/approached/reached/exceeded`，不自行发反向交易信号。反转必须另有结构与bar证据。
**验收**：强跌穿MM时应显示“目标触及但未确认反转”，不得机械buy。
**SOXL优先级**：高。用户已有MM问题，也容易把预测目标误读为必然支撑。

## C05：measuring gap需要背景，区间内缺口可失败
**来源**：[Ask Al: Missing swing trades, measured moves, trading spikes](https://www.brookstradingcourse.com/ask-al/missing-swing-trades-measured-moves-spikes/)，已读Question 2及Trading range days段落。
**概念/文字样例**：作者在所讨论区间日中不期待若干潜在measuring gap持续，并用“日开盘与极值”等不同锚点描述投射。这说明锚点选择并非唯一，也不能把每个小缺口当趋势延续。
**工程规格**：分别记录opening gap、micro gap、breakout-level gap，不混成一个指标；每个目标带anchor_type和价格。缺口关闭发失效事件，不删除旧预测。
**验收**：同一gap形状置于range与breakout背景，得到不同支持/反对理由；多目标并列，不能事后只留下命中的一个。
**待核实**：必须看原图才能将文中bar号转成回放测试样本。

## C06：概率不得从口述启发式复制
**来源**：[Ask Al: Trading statistics & probabilities](https://www.brookstradingcourse.com/ask-al/trading-statistics-probabilities/)，已读How do we determine probabilities原文。
**概念**：作者明确说明某些通道/楔形相关百分比属于主观指导，而非他已完成的统计测试。
**工程规格**：`probability=null`作为初始默认；保留`heuristic_strength`与其证据。若日后给概率，必须附定义、样本量、品种/周期、时间区间、成本处理、样本外结果和置信区间。
**验收**：规则得分80不得显示80%胜率。禁止LLM把“强”改写成“确定/必然”。

## C07：双底与楔形可重叠，不能双重计算独立证据
**来源**：[5 Steps to finding today's trades](https://www.brookstradingcourse.com/trading-strategies/5-steps-to-finding-todays-trades/)，已读Look for Double Tops and Bottoms段落。
**概念/文字样例**：作者使用宽松的双顶/底概念；同一位置可能同时被解释为楔形和双顶，并结合反向信号bar观察。
**工程规格**：每个pattern保留共享的pivot IDs；聚合解释时标记重叠证据，而不是假设两种形态独立并将概率相乘。严格等低点与宽容差测试作为两个detector版本。
**验收**：一个三推末端同时产生DT与wedge时，UI显示一个结构簇及两个解释，不推送两次同方向警报。
**待核实**：原图与视频未观看，不能按文字声称识别出作者的全部标注。

## C08：H2是第二次尝试，命名随背景变化
**来源**：[Emini October wedge rally testing July all time high](https://www.brookstradingcourse.com/analysis/emini-october-wedge-rally-testing-july-all-time-high/)，2019-10-19 Al署名回复，已读回复段落。
**概念**：作者解释H1/H2可用于趋势或区间，但首次熊趋势向上尝试往往采用其他命名；第二次买入尝试则可叫H2。
**工程规格**：存储机械`attempt_count`与语境标签分开。命名不得决定信号方向质量；H2 in bull pullback与H2 countertrend必须不同context。
**验收**：连续两根高点上涨不能自动变H2；中间需有新的回调/尝试失败episode。重置策略是项目假设，要在文档中显式列出。

## C09：止盈不等于反向开仓
**来源**：[Ask Al: Trade management examples](https://www.brookstradingcourse.com/ask-al/trade-management-examples/)，已读正文示例段落。
**概念/文字样例**：作者在连续强阳线背景下，会考虑在均线处为已有多头止盈，但并不因此愿意新开空头。
**工程规格**：输出角色分开：`manage_existing_long / new_short_setup`；没有持仓上下文时只说“潜在获利了结区”，不说“卖出做空”。
**验收**：触及阻力时不能同时给所有用户同一个“sell”含混标签。

## C10：一分钟是工程输入，不是教学默认周期的等价替代
**来源**：[Ask Al: Brazil price action community video podcast](https://www.brookstradingcourse.com/ask-al/brazil-price-action-video-podcast/)，已读时间周期相关逐字稿段落，未看视频。
**概念**：作者描述自己选择5分钟与决策舒适度有关，更低周期会增加压力；这不是“一分钟必不可能盈利”的证明。
**工程规格**：SOXL先保留1分钟原始事件，5分钟已收盘背景作独立实验配置；推送节流与重复合并，不用更多警报假装更多优势。不能偷用正在形成的5分钟最终OHLC。
**验收**：09:33只能访问已完成的高周期bar；等待09:35结束后才更新完整5分钟背景。

## 建议实现顺序
1. 数据时间语义、事件schema、closed-bar、缺口与修订审计。
2. 基础bar/摆动→背景→双底/顶、H1/H2与MM；先具备观望输出。
3. 突破/回踩/失败生命周期，重叠形态去重。
4. 用公开直播逐bar标注，做候选/确认与误报审计。
5. 再研究MTR/final flag/climax等主观、嵌套结构。

## 仍需观看/视觉核验
- 免费12A Market Cycle完整视频：验证背景切换示例而非仅概念。
- 免费20A/B MM样片：锚点选择、替代投射及失败情形。
- 5 Steps to finding today's trades：逐图核实宽松DB/DT与楔形的重叠。
- 2023/2024公开交易室录像：逐bar保留原始时间戳，分清Al与其他讲师。
- 本文件中的所有历史bar编号示例均须核对图像，才能作为gold labels。
- manual完整25章只有12章公开；本轮不访问会员内容。已读的三个manual章节不能代表整套课程。

## 数据实验边界（协调补充）
2026-11-17 SOXL已用于构思，不得称盲测。过去三个月样本按时间顺序分成开发、验证、冻结留出；若查看留出后改规则，该段须降级为开发证据。真正前向评估在规则和参数冻结之后开始，交易成本和信号可用时间统一。单日回放只能用于事件审计，不足以证明盈利优势。
