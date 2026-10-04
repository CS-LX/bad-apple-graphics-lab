# Bad Apple Graphics Lab

用四种图像处理与计算几何方法重新呈现《Bad Apple!!》：四叉树结构差分、距离场时间差分、持续 Delaunay 网格连边变化、时空 BSP 分块。每一版都由脚本计算，颜色和几何结构有明确含义。

本仓库提供脚本、依赖和使用说明。**原始视频、音频、抽帧、字体和渲染成片不随仓库分发**；请自行准备输入素材。四部 B 站标题和简介见 [docs/bilibili-copy.md](docs/bilibili-copy.md)。

## 快速开始

建议使用 Python 3.12。在仓库根目录创建独立环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

macOS / Linux 的环境激活命令为：

```bash
source .venv/bin/activate
```

安装 [FFmpeg](https://ffmpeg.org/download.html)，将包含 `ffmpeg` 和 `ffprobe` 的目录加入 `PATH`，重新打开终端后检查：

```text
ffmpeg -version
ffprobe -version
```

FFmpeg 需要支持 `libx264` 和 AAC。Python 依赖负责数值计算与绘图，Pillow 生成静态警告卡，FFmpeg 负责读写视频和合并音轨；无需 GPU，也不依赖 `drawtext`。

可通过环境变量指定工具和字体位置：

| 变量 | 用途 |
| --- | --- |
| `FFMPEG_BIN` | `ffmpeg` 可执行文件的完整路径，优先于 `PATH` |
| `FFPROBE_BIN` | `ffprobe` 可执行文件的完整路径，优先于 `PATH` |
| `FONT_FILE` | 本地字体文件的完整路径；中文警告卡请指定支持中文的字体 |

例如在 Windows PowerShell 中使用系统已有的微软雅黑：

```powershell
$env:FONT_FILE = "C:/Windows/Fonts/msyh.ttc"
```

脚本会尝试常见系统中文字体；未找到时警告卡使用英文提示。字体文件由用户本地提供，不需要上传到仓库。

将输入视频放到：

```text
assets/bad_apple.mp4
```

本次完整复现使用 **960×720、30 fps、6572 帧**的版本，视频时长约 **219.066667 秒**，含 AAC 音轨。素材文件出处见 [NPCat/bad-apple-bot](https://github.com/NPCat/bad-apple-bot)。当前整片打包和复用检查围绕这个输入规格编写；不同剪辑、帧数或时长的版本需要调整检查逻辑，不能只替换同名文件就假定结果一致。

一条命令计算四版并生成本地观看页：

```text
python scripts/render_all.py
```

入口会并行启动尚未完成的渲染，并复用通过完整性检查的中间视频或交付视频。已完成的交付物仍在时，删除 `output/` 不会导致无意重算。修改参数、代码或替换输入后，如需全部重算：

```text
python scripts/render_all.py --force
```

全片渲染主要占用 CPU，时间随处理器和存储速度变化。进度与错误见 `logs/`，中间视频及计算统计见 `output/`。首次运行请预留数 GB 磁盘空间。

## 输出

| 文件 | 内容 |
| --- | --- |
| `deliverables/A_quadtree_events.mp4` | A：四叉树结构变化 |
| `deliverables/B_sdf_time_derivative.mp4` | B：距离场时间差分 |
| `deliverables/C_delaunay_connectivity.mp4` | C：持续网格连边变化 |
| `deliverables/D_spacetime_bsp.mp4` | D：时空 BSP 叶块 |
| `deliverables/00_four_way_comparison.mp4` | 四画面对比 |
| `deliverables/preview_12s.mp4` | 12 秒正文加 3 秒静态提示，共 15 秒 |
| `deliverables/index.html` | 本地观看页，可直接用浏览器打开 |
| `deliverables/validation.json` | 打包时的帧数、尺寸、时长等检查 |
| `deliverables/project.json` | 算法说明与运行环境记录 |

单版正文为 960×720、30 fps；四画面对比版为 1280×960。音轨由输入素材合入。`output/` 的渲染中间视频不带音轨。

发布包装中，**A、B、C，以及包含这些画面的对比版，片头加入 3 秒静态光敏提示**；D 只保留画面中的 `x`、`y`、`time +2s` 轴说明。提示期间无声，A/B/C 的正文与音轨一起后移 3 秒，音轨转码一次 AAC；D 直接复制源音轨。对比版会去掉 A/B/C 已有片头后同步拼接，再统一添加一次提示，避免 D 提前播放。

| 发布文件 | 帧数 | 视频时长 |
| --- | ---: | ---: |
| A / B / C | 6662 | 约 222.066667 秒 |
| D | 6572 | 约 219.066667 秒 |
| 四画面对比 | 6662 | 约 222.066667 秒 |

四个正文渲染中间文件仍各为 6572 帧。

警告卡的中英文文案与版式见 [scripts/presentation.py](scripts/presentation.py)。卡片采用粗体黑体、无边框，保持静止和无声，不闪烁，也不播放倒计时动画。

## 四种方法

### A · 四叉树结构差分

每帧先缩放、二值化，再生成四叉树。比较相邻两帧固定坐标上的**内部节点集合**：新增节点画青色，消失节点画橙色，对应分裂与合并；事件保留最长 0.5 秒的衰减余辉。

这里做的是树结构本身的差分。图像置于 512×512 的黑色填充域，实际图像区域为 512×384；最小叶块边长 4，混色阈值 1.8%。因此它是近似二值树，不是原帧的无损编码。固定黑边也会影响靠近边界的分裂。事件数量是节点集合增删数，不是最短树编辑序列。

### B · 平滑距离场的时间差分

对二值轮廓计算离散有符号距离场，内部为负、外部为正，并进行轻微高斯平滑。再计算相邻时刻的有限差分：**青色代表距离值减小，橙色代表距离值增大**。彩线是等距线，浅色边缘显示当前轮廓附近的零水平集。

通常采用中心差分；首尾或纯色帧旁使用可用的单侧差分。纯色帧没有图内轮廓，输出暗背景。平滑与离散采样使它不再是严格连续欧氏距离场；它也不是物理波传播、压力场或精确法向速度。

### C · 持续 Delaunay 网格的连边变化

采样点拥有固定 ID，由近似光流推动，并通过回弹、排斥和位移限制保持稳定。每帧计算 Delaunay 三角剖分，对比相邻时刻的连边集合：**青色表示新增边，橙色表示删除边**。淡色三角面与基础网格亮度来自原图采样，用来保留画面辨识度。

检测到强硬切时，采样点回到同一初始网格，并清空跨切换余辉。光流在黑白剪影内部并不唯一，所以该网格是算法驱动的可视化，不是精确物体追踪。它展示采样时刻的连边变化，没有逐一求解所有基础边翻转事件。

### D · 时空 BSP 叶块时间跨度

把低分辨率视频视作 `(x, y, t)` 二值体，按固定 2 秒数据段做轴对齐的二叉空间分割，直到每个叶块内部同色。每段都从输出叶块重建输入体素并检查误差；画面只显示白色叶块。

输入以 **120×90、15 Hz** 采样，以 **30 fps** 扫描连续移动的两秒时窗。青蓝色叶块的时间跨度短，偏黄橙色的更长，达到约 1 秒后使用长跨度色。这里的颜色表示**叶块在当前分段内的时间跨度**；跨段不合并，不代表整片中区域的完整寿命。精确重建针对低分辨率二值体，不是原始视频所有像素。

## 单独运行

以下命令只生成对应无声中间视频：

```text
python scripts/render_fields.py tree
python scripts/render_fields.py sdf
python scripts/render_mesh.py
python scripts/render_spacetime.py
```

四个中间视频齐备后，重新执行合并与观看页生成：

```text
python scripts/finish_videos.py
```

只重新包装指定版本或更新观看页：

```text
python scripts/finish_videos.py --only A B C --mux-only --force
python scripts/finish_videos.py --gallery-only
```

`--only` 可选 A、B、C、D；`--mux-only` 跳过对比版生成；`--force` 强制重新生成包装结果。

先验证某一段算法可使用 `--start`、`--duration` 和独立输出路径，例如：

```text
python scripts/render_fields.py tree --start 45 --duration 6 --output output/test_tree.mp4
python scripts/render_fields.py sdf --start 45 --duration 6 --output output/test_sdf.mp4
python scripts/render_mesh.py --start 45 --duration 6 --output output/test_mesh.mp4 --tag test_mesh
python scripts/render_spacetime.py --start 45 --duration 6 --output output/test_spacetime.mp4
```

短片输出只用于局部查看，不替代整片打包所需的完整中间文件。更多参数见各脚本的 `--help`。

## 依赖与验证范围

`requirements.txt` 使用兼容版本范围。制作本次成片时实际使用 Python 3.12、NumPy 2.5.1、SciPy 1.18.1、Pillow 12.3.0、opencv-python-headless 5.0.0.93；这些是运行记录，不要求读者安装完全相同的版本组合。

最初无警告片头的四个正文均检查过完整帧数、分辨率和时长；A/B 完整解码，C/D 的中间视频完整解码，最终合并文件的视频载荷与中间片一致。原曲直拷版本通过 AAC 数据包哈希核对。当前 A/B/C 发布包装添加了片头并重编码音轨，因此不能用“整条音轨哈希等于原片”验证这些文件；D 保留原音轨直拷。历史正文 QA 不能替代新增片头后的成片检查。

重新运行 `finish_videos.py` 生成的是容器参数检查；它不替代完整解码检查，也不自动重建本次人工整理的 QA 报告。

发布后可运行专门的校验脚本：

```text
python scripts/validate_release.py
```

它检查四部成片的帧数与完整解码、A/B/C 静态警告及正文起点、3 秒静音与原曲偏移、D 原音轨直拷，输出 `deliverables/release_qa.json`。如果无声中间文件已清理，仅跳过依赖中间片的画面对照；保留输入素材时其余核心检查仍可运行。

完整交付并检查后，可以删除 `output/`、`logs/`、`previews/` 和 `assets/frame_*.png`。保留 `deliverables/`、`assets/bad_apple.mp4`、脚本和 Python 运行环境。

## 来源与署名

- 原作动画：あにら（Anira），[《【東方】Bad Apple!! ＰＶ【影絵】》](https://www.nicovideo.jp/watch/sm8628149)。
- 音乐：《Bad Apple!! feat.nomico》，[Alstroemeria Records](https://alst.net/)，演唱 nomico；原曲来自 ZUN 的东方 Project。
- 本次处理所用视频文件来源：[NPCat/bad-apple-bot](https://github.com/NPCat/bad-apple-bot)。

这些署名用于说明素材来源，不表示动画或音乐由本仓库作者创作。动画、音频和字体的权利属于各自权利人。公开检索尚未找到四种具体组合的直接同类作品，但这不能证明全网首创。
