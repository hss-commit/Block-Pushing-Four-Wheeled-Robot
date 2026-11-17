"""Generate an exact ArUco asset and a physical-size HTML print sheet."""
from pathlib import Path
import cv2
import numpy as np


def main():
    folder = Path(__file__).with_name('markers')
    folder.mkdir(exist_ok=True)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(dictionary, 0, 600)
    padded = np.pad(marker, 120, constant_values=255)
    ok, encoded = cv2.imencode('.png', padded)
    assert ok
    encoded.tofile(folder / 'aruco-4x4-50-id0.png')
    (folder / '打印我方定位码.html').write_text('''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><title>我方小车定位码</title>
<style>@page{size:A4;margin:20mm}body{font:16px sans-serif;color:#000;background:#fff}
.tag{width:70mm;text-align:center;break-inside:avoid}.tag img{width:70mm;height:70mm;image-rendering:pixelated}
button{padding:10px}@media print{button{display:none}} .ruler{width:50mm;border-top:1px solid;margin-top:10mm}</style>
<h1>我方小车定位码</h1><p>ArUco · DICT_4X4_50 · ID 0</p>
<button onclick="window.print()">打印定位码</button>
<div class="tag"><p>↑ 车头方向 ↑</p><img src="aruco-4x4-50-id0.png" alt="ID 0"><p>保持这个方向贴在车顶</p></div>
<p>打印选择“实际大小 / 100%”，关闭“适合页面”。黑色正方形边长应为 50 mm，白边保留。</p>
<p>量一下实物黑色正方形边长。如果不是5厘米，在启动菜单 M 中填实际尺寸。</p>
<p>贴在平整硬板上，尽量放在车体中心，避免反光。不要贴第二张相同ID到其他车上。</p>
<div class="ruler">这条线应长 50 mm</div>
</html>''', encoding='utf-8')
    print(folder)


if __name__ == '__main__':
    main()
