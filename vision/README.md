# 手机照片识别 · Python + OpenCV

从项目目录双击 `启动视觉识别.cmd`，选择手机照片即可开始。当前版本是真正调用 OpenCV 的本地 Python 程序，照片不会上传。

1. 照片中我方半场放在下方，场地内侧四角都要入镜。用 JPG 或 PNG；HEIC 先转 JPG。
2. 按 **左上 → 右上 → 右下 → 左下** 点击场地内角，按 Enter 确认。右键撤销上一个点，R 清空重选。
3. 点击校正后图中一个方块的中心取色。另一窗口显示黑白筛选结果；白色应该对应方块。
4. 调节 H（色相）、S（饱和度）、V（亮度）容差和 Min area（最小区域面积）。识别太少可适当增大容差，背景也变白时减小容差或重新取色。
5. 按 S 保存框选图、黑白图和坐标 JSON。每次保存生成 `vision/results/` 下的独立目录。Esc 或关闭窗口退出。

输出坐标单位为毫米，按 1200 × 1200 mm 场地换算，原点在画面左下，x 向右，y 向上。坐标系不代表胜负方向。窗口标注使用英文，以兼容 OpenCV 自带窗口。

## 在 VS Code 中运行

打开整个项目文件夹，打开终端并执行：

```powershell
.\.venv\Scripts\python.exe .\vision\photo_vision.py
```

没有照片可先用合成演示图练习：

```powershell
.\.venv\Scripts\python.exe .\vision\photo_vision.py --demo
```

若安装了 VS Code Python 扩展，选择解释器时选项目内 `.venv\Scripts\python.exe`。当前环境由本机自带 Python 3.12 创建；迁移电脑或移除该 Python 后需要重建环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\vision\requirements.txt
```

## 本版范围与校验

已实现照片读取、四角透视校正、HSV 分割（含红色色相跨界）、形态学清理、连通区域和坐标输出。通过合成图片检查处理链路；真实手机照片的颜色、畸变和误差尚需现场验证。相连方块可能作为一个区域输出，所以区域数不等于方块数。本版没有相机畸变校正、方块高度补偿、视频多帧确认、AprilTag 或车辆控制；单张图片测试不能证明实车定位精度。

运行处理链路自检：

```powershell
.\.venv\Scripts\python.exe .\vision\test_photo_vision.py
```

原 `视觉照片识别.html` 为先前的网页试验，后续开发以这里的 Python + OpenCV 为准。
