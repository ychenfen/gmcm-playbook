# 多核切图与调度的数学形式化

本文件是论文正文建模部分的底稿。记号与赛题一致。

## 1. 问题实例

计算图 $G=(V,E)$，$V=T\cup O$，$T$ 为张量节点、$O$ 为操作节点，$T\cap O=\varnothing$，
$E\subseteq(T\times O)\cup(O\times T)$。

- 张量 $t\in T$：位置 $\mathrm{pos}(t)\in\{\mathrm{DDR},\mathrm{L1},\mathrm{UB}\}$，字节数 $s_t\ge 0$。
- 操作 $o\in O$：类型、流水线 $\pi(o)\in\{\mathrm{PIPE\_M},\mathrm{PIPE\_V},\mathrm{PIPE\_MTE2},\mathrm{PIPE\_MTE3}\}$、周期数 $c_o\ge 0$。
- 可分配集合 $O^\ast=\{o\in O:\mathrm{type}(o)\notin\{\mathrm{COPY\_IN},\mathrm{COPY\_OUT}\}\}$。

**收缩依赖图**。把张量作为中转、并跨过 COPY 节点，得到 $O^\ast$ 上的有向图
$D=(O^\ast,A)$，其中 $(u,v)\in A$ 当且仅当 $G$ 中存在 $u\to\cdots\to v$ 的有向路径且内部
节点均为张量或 COPY 节点。$D$ 无环（赛题保证原图无环）。

## 2. 决策变量

给定核数 $N$。设子图集合 $S=\{1,\dots,|S|\}$（$|S|$ 不预先固定，见 §5）。

$$
x_{vs}=\begin{cases}1,&\text{操作 }v\in O^\ast\text{ 归入子图 }s\\0,&\text{否则}\end{cases}
\qquad
y_{sn}=\begin{cases}1,&\text{子图 }s\text{ 分配到核 }n\\0,&\text{否则}\end{cases}
$$

$z_{ss'}\in\{0,1\}$：同核子图 $s$ 排在 $s'$ 之前。

## 3. 可行性约束

**(C1) 划分**：每个可分配操作属于且仅属于一个子图
$$\sum_{s\in S}x_{vs}=1,\qquad \forall v\in O^\ast.$$

**(C2) 核归属**：每个非空子图分配到且仅分配到一个核
$$\sum_{n=1}^{N}y_{sn}=1,\qquad \forall s\in S.$$

**(C3) 商图无环**。定义子图间依赖
$$s\to s' \iff \exists (u,v)\in A,\ x_{us}=x_{vs'}=1,\ s\ne s'.$$
要求商图 $\bar D=(S,\bar A)$ 无环。等价的线性化写法是引入子图秩 $r_s\in\mathbb{Z}_{\ge 0}$ 并要求
$$r_{s'}\ge r_s+1-M\left(2-x_{us}-x_{vs'}\right),\qquad \forall (u,v)\in A,\ s\ne s',$$
其中 $M$ 为足够大的常数。$r$ 存在即等价于 $\bar D$ 无环。

**(C4) 同核顺序相容**：若 $s\to s'$ 且二者同核，则 $s$ 必须排在 $s'$ 之前
$$z_{ss'}=1,\qquad \forall\, s\to s',\ \exists n:\ y_{sn}=y_{s'n}=1.$$

## 4. 目标与代价

### 4.1 通信量

设 $\tau(u)$ 为操作 $u$ 的输出张量集合。跨子图边界的张量需经 DDR 中转：

- **场景 A**（每个子图独立成 Task）：边界由子图决定
$$B_A=\sum_{u\in O^\ast}\ \sum_{t\in\tau(u)} s_t\cdot\mathbb{1}\!\left[\exists v:(u,v)\in A,\ \sigma(u)\ne\sigma(v)\right]\cdot 2,$$
其中 $\sigma(\cdot)$ 表示所属子图，系数 2 来自 COPY\_OUT + COPY\_IN 各一次。

- **场景 B**（同核子图合并为一个 Task）：边界由**核**决定，同核子图边界不产生搬运
$$B_B=\sum_{u\in O^\ast}\ \sum_{t\in\tau(u)} s_t\cdot\mathbb{1}\!\left[\exists v:(u,v)\in A,\ \kappa(u)\ne\kappa(v)\right]\cdot 2,$$
$\kappa(\cdot)$ 表示所属核。**这是场景 A/B 经济学差异的根源**：$B_B\le B_A$，且切分越细差距越大。

### 4.2 Makespan

精确的 makespan 由赛题评估器的事件模拟给出（多流水线、DDR 带宽公平共享、
缓存换入换出），无法写成闭式。论文采用**两层处理**：

1. **下界/参考模型**（可解析）：忽略带宽争用与缓存换出，仅计算力、关键路径、
   强制 DDR 流量与跨核固定同步延迟，得可达参考 $\underline{L}(N)$。
2. **真实目标**：以官方评估器 $\mathcal{E}(\cdot)$ 为黑箱目标函数，启发式求解。

### 4.3 松弛 MILP（用于小规模精确求解与启发式合理性论证）

固定子图数 $|S|=N$（每核恰一个子图），忽略流水线重叠与带宽争用，用
$$L_n=\sum_{v}\max\big(c_v\mathbb{1}[\pi(v)=\mathrm{M}],\,c_v\mathbb{1}[\pi(v)=\mathrm{V}]\big)x_{v,n}
+\frac{B(\mathbf{x})}{W}$$
近似核 $n$ 的忙时（$W=60$ bytes/cycle），则
$$\min_{\mathbf{x},\mathbf{y}}\ \max_{n} L_n \quad \text{s.t. (C1)-(C4)}$$
是一个**带无环约束的平衡图划分**问题（acyclic balanced $N$-way partitioning），已知
NP 难。该松弛用于：(a) 在小用例上用求解器得精确解，与启发式对照；
(b) 论证"子图数—通信量—并行度"三者的取舍关系。

## 5. 子图数的作用（实测支撑）

$|S|$ 不是自由参数，而是代价函数的一部分：

- **场景 A**：每个子图是一个 Task，激活需等待（同核 100 cycles、跨核 1000 cycles），
  且所有跨 Task 数据强制经 DDR。$|S|$ 增大直接抬高 $B_A$ 与激活延迟之和。
- **场景 B**：同核子图合并，$|S|$ 本身不计 Task 开销，但跨核 COPY 的
  500 cycle 同步延迟会沿关键路径累积，相位深度（路径上的换核次数）成为代价。

实测贯穿全部 5 个算法与两个场景：**子图数过大必然劣化**。这是本题最强的经验规律，
也是构造算法的首要约束。

## 6. 待补

- [ ] 小用例上的 MILP 精确解与启发式对照实验
- [ ] 相位深度与 makespan 的定量关系（场景 B）
- [ ] 问题 3 只读 L2 Cache 的形式化（FIFO 命中率、带宽池隔离）
