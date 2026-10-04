# 四部视频的 B 站标题与简介

下面各段简介可以直接复制到投稿页。源码与使用说明：[CS-LX/bad-apple-graphics-lab](https://github.com/CS-LX/bad-apple-graphics-lab)。

## A · 四叉树结构差分

**标题：Bad Apple!!，但我只能看见四叉树的分裂与合并**

**简介：**

光敏提示：本视频包含快速闪烁和高对比图案，片头有 3 秒静态警告。对闪光敏感的观众请勿继续观看；如感到不适，请立即停止观看。

把每一帧变成一棵四叉树，再看这棵树和上一帧相比，哪里分裂了，哪里合并了。轮廓复杂的地方不断细分，大块同色区域则可以合成更大的格子。

青色是新增的内部节点，橙色是消失的内部节点，留下半秒衰减余辉。人物一动，细格子就在轮廓附近拆开、消退；留下来的轨迹又拼出了熟悉的动作。

这里比较的是树结构本身，采用近似二值树。暂停时可以看节点，播放时可以看动作。完整脚本、参数和复现方法都放在下面的仓库里。

源码与使用说明：https://github.com/CS-LX/bad-apple-graphics-lab

原作动画：あにら（Anira）《【東方】Bad Apple!! ＰＶ【影絵】》
https://www.nicovideo.jp/watch/sm8628149
音乐：Bad Apple!! feat.nomico / Alstroemeria Records，演唱 nomico
https://alst.net/
本次输入素材文件来源：https://github.com/NPCat/bad-apple-bot

**可用标签：** Bad Apple、东方Project、四叉树、算法可视化、计算机图形学、Python

## B · 距离场时间差分

**标题：Bad Apple!!，但我对每个点到轮廓的距离求了时间导数**

**简介：**

光敏提示：本视频包含快速闪烁和高对比图案，片头有 3 秒静态警告。对闪光敏感的观众请勿继续观看；如感到不适，请立即停止观看。

如果每个像素都记录自己离人物轮廓有多远，再看这个距离随时间怎么变，整个背景也会跟着人物一起动。原本只是黑白剪影的画面，会长出一圈圈延伸到屏幕边缘的等距线。

做法是先算平滑的离散有符号距离场，再做时间差分。青色表示距离值减小，橙色表示增大；彩线连接距离相同的位置，浅色线勾出当前轮廓附近。

这些线看起来像波纹，实际来自距离的变化，没有模拟水波或压力。纯色帧没有图内轮廓，所以显示暗背景。计算方法和完整复现脚本见下面的仓库。

源码与使用说明：https://github.com/CS-LX/bad-apple-graphics-lab

原作动画：あにら（Anira）《【東方】Bad Apple!! ＰＶ【影絵】》
https://www.nicovideo.jp/watch/sm8628149
音乐：Bad Apple!! feat.nomico / Alstroemeria Records，演唱 nomico
https://alst.net/
本次输入素材文件来源：https://github.com/NPCat/bad-apple-bot

**可用标签：** Bad Apple、东方Project、距离场、图像处理、算法可视化、Python

## C · 持续网格连边变化

**标题：Bad Apple!!，但三角网格一直在断线和重连**

**简介：**

光敏提示：本视频包含快速闪烁和高对比图案，片头有 3 秒静态警告。对闪光敏感的观众请勿继续观看；如感到不适，请立即停止观看。

给画面铺上一张三角网格，让有固定 ID 的点跟着近似光流移动，再观察它们之间的连接如何变化。点一直在，邻居却可能随着人物动作不断更换。

每帧进行 Delaunay 三角剖分：青色是新出现的边，橙色是刚消失的边。淡色三角面保留原图亮度，亮线则把网格的变化单独显出来，看起来像不断拆开又接上的电路。

这里展示的是相邻采样时刻的连边变化，没有逐个求解基础边翻转。点的运动经过稳定处理，画面强切换时会重置。算法细节和脚本都放在仓库里。

源码与使用说明：https://github.com/CS-LX/bad-apple-graphics-lab

原作动画：あにら（Anira）《【東方】Bad Apple!! ＰＶ【影絵】》
https://www.nicovideo.jp/watch/sm8628149
音乐：Bad Apple!! feat.nomico / Alstroemeria Records，演唱 nomico
https://alst.net/
本次输入素材文件来源：https://github.com/NPCat/bad-apple-bot

**可用标签：** Bad Apple、东方Project、Delaunay、计算几何、光流、算法可视化

## D · 时空 BSP

**标题：Bad Apple!!，但我把时间切成了一堆方块**

**简介：**

把横纵坐标和时间放进同一个三维空间，视频就变成了一块可以切开的数据体。一个画面里停留很久的白色区域，会沿时间方向延伸成更长的方块。

这次用 BSP 二叉空间分割，把固定两秒内的黑白体素切成同色长方体，只画出白色叶块。最前面的切面对应当前画面，往斜后方延伸的是接下来两秒。

青蓝色代表时间跨度短，偏黄橙色代表跨度长。这个跨度属于当前两秒分块中的叶块，不是追踪某个区域在整部视频里活了多久。

原图以 120×90、15fps 采样，画面以 30fps 连续扫描。每段都做了体素重建检查，显示的方块来自实际分割。画面只保留 x、y 和 time +2s 轴说明，方便看清空间与时间的关系。

源码与使用说明：https://github.com/CS-LX/bad-apple-graphics-lab

原作动画：あにら（Anira）《【東方】Bad Apple!! ＰＶ【影絵】》
https://www.nicovideo.jp/watch/sm8628149
音乐：Bad Apple!! feat.nomico / Alstroemeria Records，演唱 nomico
https://alst.net/
本次输入素材文件来源：https://github.com/NPCat/bad-apple-bot

**可用标签：** Bad Apple、东方Project、BSP、数据可视化、计算机图形学、Python

## 发布用的统一说明

A/B/C 和包含它们的对比版使用 3 秒静态无声警告片头，采用粗体黑体、无边框；D 只保留 x、y 和 time +2s 轴说明。发布文案不使用“全网首创”“首次实现”等无法证实的说法。

实际静态片头的中英文内容以 [scripts/presentation.py](../scripts/presentation.py) 为准。

## 投稿字段长度的核对记录

核对日期：2026-10-04。四个标题都刻意保持简短。

[B 站官方开放平台错误码文档](https://open.bilibili.com/doc/4/8673959e-f7bb-56e6-6e68-d225f971b81b)的公开检索内容列有稿件标题超过 **80 个字符**的错误（123030 / 123033）。该页面也列有“稿件描述长度太长”的错误，但本次没有查到可直接核实的统一简介字符上限，因此这里不把第三方资料中的数值当作官方规则。实际投稿仍以当前[创作中心](https://member.bilibili.com/platform/upload/video/frame)的字段计数和提示为准。
