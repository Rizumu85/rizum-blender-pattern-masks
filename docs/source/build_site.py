"""Build the documentation site into site/ (static HTML, published with GitHub
Pages by .github/workflows/pages.yml).

    python docs/source/build_site.py

Text: docs/content/<lang>.json (drafted with Gemini from the manual, then
checked against the manual and the code). Images: site/img/ (made by the
scripts next to this one). Nothing here needs a package beyond Python.
"""
import html
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SITE = os.path.join(REPO, "site")
CONTENT = os.path.join(REPO, "docs", "content")
REPO_URL = "https://github.com/Rizumu85/rizum-blender-pattern-masks"

LANGS = [("en", "English"), ("zh-CN", "简体中文"), ("ja", "日本語")]

# words the site itself needs, outside the drafted text
UI = {
    "en": {"g_start": "Start", "g_ideas": "How it works", "g_ref": "Reference", "docs": "Documentation", "theme": "Light or dark theme", "repo": "GitHub", "prev": "Previous", "next": "Next",
           "on_page": "On this page", "lang": "Language", "menu": "Pages",
           "style": "Style", "dashed": "Dashed", "zigzag": "Zigzag", "from_edge": "From Edge",
           "width": "Width", "length": "Length", "gap": "Gap", "height": "Height", "corner": "Corner Inset",
           "loops": "Follow Loops", "unrolled": "Unrolled", "loops_note": "Squares follow the mesh's loops and keep one size. Small forks appear where the piece widens.", "unrolled_note": "The piece is laid flat with the marked edge straight. No forks, but the squares grow toward the hem. For open panels, not closed tubes.",
           "workflow": ["Mark edges", "Tune", "Bake", "Paint"],
           "reference_note": "Green: the line art's own edges. Red: edges the stitches leave out."},
    "zh-CN": {"g_start": "入门", "g_ideas": "功能讲解", "g_ref": "参考", "docs": "文档", "theme": "切换浅色或深色主题", "repo": "GitHub", "prev": "上一页", "next": "下一页",
              "on_page": "本页内容", "lang": "语言", "menu": "页面",
              "style": "样式", "dashed": "虚线", "zigzag": "锯齿", "from_edge": "离边距离",
              "width": "宽度", "length": "长度", "gap": "间隔", "height": "高度", "corner": "尖角内缩",
              "loops": "顺布线", "unrolled": "展开", "loops_note": "方格顺着网格布线走，大小始终一致。衣片变宽的地方会出现小分叉。", "unrolled_note": "把衣片摊平、标记的边拉直再铺。不会分叉，但方格越往下摆越大。适合开口的衣片，不适合闭合的筒形。",
              "workflow": ["标边", "调参数", "烘焙", "绘制"],
              "reference_note": "绿色：线稿自己的边。红色：缝线去掉的边。"},
    "ja": {"g_start": "はじめに", "g_ideas": "しくみ", "g_ref": "リファレンス", "docs": "ドキュメント", "theme": "ライトまたはダークテーマ", "repo": "GitHub", "prev": "前へ", "next": "次へ",
           "on_page": "このページの内容", "lang": "言語", "menu": "ページ",
           "style": "Style", "dashed": "Dashed", "zigzag": "Zigzag", "from_edge": "From Edge",
           "width": "Width", "length": "Length", "gap": "Gap", "height": "Height", "corner": "Corner Inset",
           "loops": "Follow Loops", "unrolled": "Unrolled", "loops_note": "マスはメッシュのループに沿い、大きさは一定です。パーツが広がる所に小さな分かれ目ができます。", "unrolled_note": "パーツを平らに広げ、マークした辺をまっすぐにして敷きます。分かれ目はできませんが、裾に向かうほどマスが大きくなります。開いたパーツ向きで、閉じた筒には向きません。",
           "workflow": ["辺をマーク", "調整", "ベイク", "ペイント"],
           "reference_note": "緑：線画レイヤー自身の辺。赤：ステッチが外した辺。"},
}

# words of the practice sandbox
PRACTICE = {
    "en": {
        "stitches": "Stitches",
        "lineArt": "Line Art",
        "auto": "Auto",
        "fromEdge": "From Edge",
        "width": "Width",
        "none": "None",
        "add": "Add",
        "remove": "Remove",
        "select": "Select",
        "clear": "Clear",
        "pick": "Eyedropper",
        "showEdges": "Show Edges",
        "visible": "Show and bake",
        "skip": "Skip this step",
        "restart": "Start over",
        "edges": "Edges",
        "reference": "Reference",
        "corners": "Sharp Corners",
        "flip": "Flip Side",
        "demos": {
            "flow": {
                "steps": [
                    "Press **+** next to the list and choose **Stitches**.",
                    "Click the four scallops of the hem, then **+** on the **Edges** row.",
                    "Drag **From Edge** to 6 mm.",
                    "Press **Bake 1 Mask**."
                ],
                "results": [
                    "A **Stitches** layer is in the list, with its settings below it.",
                    "The hem is now this layer's edges (green), and the stitches follow it.",
                    "The stitches now sit {from} in from the hem, measured on the model.",
                    "Your first mask: white stitches on black, laid out as in the UVs."
                ],
                "done": "Switch between the model and the mask with the tabs at the top left."
            },
            "list": {
                "steps": [
                    "Click the eye on the **Stitches** row."
                ],
                "results": [
                    "The stitches are hidden, and the bake will skip them."
                ],
                "done": "Click the eye again to bring them back."
            },
            "edges": {
                "steps": [
                    "Click the four scallops, then **+** on the **Edges** row.",
                    "Click one scallop, then **−**."
                ],
                "results": [
                    "The hem is now this layer's edges (green), and the stitches run along it.",
                    "That scallop is no longer an edge of this layer, so the stitches stop at both its ends."
                ],
                "done": "Try **×** to clear the edges, or the arrow to select them again."
            },
            "reference": {
                "steps": [
                    "Click the link icon at the end of the **Edges** row, then **Stitches**.",
                    "Click the leftmost scallop, then **−** on the **Edges** row."
                ],
                "results": [
                    "**Line Art** now uses every edge of **Stitches**: the hem turned green without marking it again. The new **Reference** row shows which layer it follows.",
                    "The leftmost scallop turned red: **Line Art** leaves it out, **Stitches** keeps it."
                ],
                "done": "Click **Stitches** in the list: its edges are unchanged."
            },
            "corners": {
                "steps": [
                    "Press **Auto** on the **Sharp Corners** row.",
                    "Click the second scallop, then **−** on the **Sharp Corners** row."
                ],
                "results": [
                    "The tip of every scallop is marked (yellow), and the stitches turn sharply there.",
                    "The tips at both its ends are cleared, and the stitches round them off."
                ],
                "done": "**+** on the same row marks them again."
            },
            "flip": {
                "steps": [
                    "Tick **Flip Side**."
                ],
                "results": [
                    "The hip line moved above its edge. The hem lines left the cloth: a border has nothing on its other side."
                ],
                "done": "Untick it and the lines come back."
            },
            "lineart": {
                "steps": [
                    "Drag **From Edge** to 3 mm.",
                    "Drag **Width** to 5 mm."
                ],
                "results": [
                    "The line moved {from} in from the hem; **From Edge** is measured to its outer side.",
                    "The outline became a {width} band: the same width everywhere, still sharp at the marked tips."
                ],
                "done": "Drag **From Edge** back to 0 and the band sits right on the edge."
            },
            "grid": {
                "steps": [
                    "Drag **Angle** to 45°.",
                    "Drag **Along Edge** or **From Edge**."
                ],
                "results": [
                    "The checks turned {angle}, still laid from the marked waist.",
                    "The checks slide along the waist, or away from it, without changing size."
                ],
                "done": "Try **Cell Size** too."
            },
            "style": {
                "steps": [
                    "Switch **Style** to **Zigzag**.",
                    "Drag **Height** to 6 mm.",
                    "Drag **From Edge** to 5 mm."
                ],
                "results": [
                    "One thread now goes back and forth, and **Height** took the place of **Gap**.",
                    "The zigzag swings {height} wide, and its peaks now touch the hem.",
                    "The whole line moved in to {from}, so the peaks are back on the cloth."
                ],
                "done": "Switch back to **Dashed** to compare."
            },
            "bakeall": {
                "steps": [
                    "Press **Bake 3 Masks**.",
                    "Change the object or material name above."
                ],
                "results": [
                    "Four files: one per layer, and two for the grid (its dark squares and its light ones). Pick one at the top left to see it.",
                    "The file names changed with it. Baking again overwrites files of the same name."
                ],
                "done": "Try **Transparent** under **Background**: the mask is kept in the alpha instead of on black."
            },
            "presets": {
                "steps": [
                    "Open the preset button next to **Stitches**, then press **+** to save.",
                    "Drag **From Edge** somewhere else, then click the saved preset.",
                    "Star the preset, then click **Default**."
                ],
                "results": [
                    "The current settings are saved under that name.",
                    "The saved settings came back: **From Edge** is where it was when you saved.",
                    "The starred preset is now the default: **Default** and new stitch layers use it."
                ],
                "done": "Click the star again to go back to the add-on's own defaults."
            }
        },
        "grid": "Grid",
        "along": "Along Edge",
        "angle": "Angle",
        "cell": "Cell Size",
        "pickInList": "Pick in List",
        "clickLayer": "Click a layer in the list",
        "stop": "Stop following",
        "length": "Length",
        "gap": "Gap",
        "bake": "Bake Masks",
        "model": "Model",
        "live": "Live Update",
        "rebuild": "Update",
        "keyEdges": "This layer's edges",
        "keyOut": "Left out",
        "keyCorners": "Sharp corners",
        "keySel": "Selected",
        "presetName": "Hem stitches",
        "preDefault": "Default",
        "preStar": "Use as the default",
        "preName": "Preset name",
        "presets": "Stitch Presets",
        "showCorners": "Show Corners",
        "style": "Style",
        "dashed": "Dashed",
        "zigzag": "Zigzag",
        "height": "Height",
        "bakeHead": "Bake",
        "background": "Background",
        "black": "Black",
        "transparent": "Transparent",
        "bake1": "Bake 1 Mask",
        "bakeN": "Bake {} Masks",
        "object": "Object",
        "material": "Material"
    },
    "zh-CN": {
        "stitches": "缝线",
        "lineArt": "线稿",
        "auto": "自动",
        "fromEdge": "离边距离",
        "width": "宽度",
        "none": "无",
        "add": "添加",
        "remove": "移除",
        "select": "选择",
        "clear": "清空",
        "pick": "吸管",
        "showEdges": "显示标记的边",
        "visible": "显示并烘焙",
        "skip": "跳过这一步",
        "restart": "重来",
        "edges": "边",
        "reference": "引用",
        "corners": "尖角",
        "flip": "翻到另一侧",
        "demos": {
            "flow": {
                "steps": [
                    "点列表右边的 **+**，选 **缝线**。",
                    "点下摆的四个扇形，再点 **边** 那一行的 **+**。",
                    "把 **离边距离** 拖到 6 mm。",
                    "点 **烘焙 1 层遮罩**。"
                ],
                "results": [
                    "列表里有了 **缝线** 层，下面是它的设置。",
                    "下摆成了这一层的边（绿色），缝线跟着它走。",
                    "缝线现在离下摆 {from}，这是在模型上量的。",
                    "第一张遮罩出来了：黑底白线，按 UV 摆放。"
                ],
                "done": "左上角的标签可以在模型和遮罩之间切换。"
            },
            "list": {
                "steps": [
                    "点 **缝线** 那一行的眼睛。"
                ],
                "results": [
                    "缝线藏起来了，烘焙时也会跳过它。"
                ],
                "done": "再点一次眼睛，就显示回来。"
            },
            "edges": {
                "steps": [
                    "点四个扇形，再点 **边** 那一行的 **+**。",
                    "点其中一个扇形，再点 **−**。"
                ],
                "results": [
                    "下摆成了这一层的边（绿色），缝线沿着它走。",
                    "这个扇形不再是这一层的边，缝线在它两头断开了。"
                ],
                "done": "试试 **×** 清空，或者用箭头把这一层的边重新选上。"
            },
            "reference": {
                "steps": [
                    "点 **边** 那一行末尾的链接图标，再选 **缝线**。",
                    "点最左边的扇形，再点 **边** 那一行的 **−**。"
                ],
                "results": [
                    "**线稿** 用上了 **缝线** 的全部边：下摆没重新标就变绿了。新出现的 **引用** 一行写着它跟随哪一层。",
                    "最左边的扇形变红了：**线稿** 不用它，**缝线** 照样保留。"
                ],
                "done": "点列表里的 **缝线** 看看：它的边一条没少。"
            },
            "corners": {
                "steps": [
                    "点 **尖角** 那一行的 **自动**。",
                    "点第二个扇形，再点 **尖角** 那一行的 **−**。"
                ],
                "results": [
                    "每个扇形的尖都标上了（黄色），缝线在这些地方拐成尖角。",
                    "它两头的尖取消了标记，缝线在那里圆滑地绕过去。"
                ],
                "done": "点同一行的 **+**，可以重新标上。"
            },
            "flip": {
                "steps": [
                    "勾上 **翻到另一侧**。"
                ],
                "results": [
                    "臀部那条线移到了边的上方。下摆的线跑到了布外：边缘的另一侧什么都没有。"
                ],
                "done": "取消勾选，线就回来了。"
            },
            "lineart": {
                "steps": [
                    "把 **离边距离** 拖到 3 mm。",
                    "把 **宽度** 拖到 5 mm。"
                ],
                "results": [
                    "线离开下摆往里移了 {from}。**离边距离** 量的是到线外侧的距离。",
                    "描边变成了 {width} 宽的色带：处处一样宽，标记的尖处还是尖的。"
                ],
                "done": "把 **离边距离** 拖回 0，色带就贴着边。"
            },
            "grid": {
                "steps": [
                    "把 **角度** 拖到 45°。",
                    "拖动 **沿边偏移** 或 **离边距离**。"
                ],
                "results": [
                    "格子转了 {angle}，仍然从标记的腰线铺起。",
                    "格子沿着腰线滑动，或者往下移开，大小不变。"
                ],
                "done": "再试试 **格子大小**。"
            },
            "style": {
                "steps": [
                    "把 **样式** 换成 **锯齿**。",
                    "把 **高度** 拖到 6 mm。",
                    "把 **离边距离** 拖到 5 mm。"
                ],
                "results": [
                    "现在是一根线来回走，面板里的 **间隔** 换成了 **高度**。",
                    "锯齿摆到了 {height} 宽，尖已经碰到下摆了。",
                    "整条线往里移到 {from}，尖又回到了布上。"
                ],
                "done": "换回 **虚线** 比较一下。"
            },
            "bakeall": {
                "steps": [
                    "点 **烘焙 3 层遮罩**。",
                    "在上面改一下物体名或材质名。"
                ],
                "results": [
                    "得到四个文件：每层一张，格纹两张（深色格和浅色格各一张）。点左上角的文件名查看。",
                    "文件名跟着变了。再次烘焙会覆盖同名的文件。"
                ],
                "done": "把 **背景** 换成 **透明** 试试：遮罩存在透明通道里，不再是黑底。"
            },
            "presets": {
                "steps": [
                    "点 **缝线** 旁边的预设按钮，再点 **+** 保存。",
                    "把 **离边距离** 拖到别的值，再点刚存的预设。",
                    "给预设点上星标，再点 **默认值**。"
                ],
                "results": [
                    "当前的参数用这个名字存下来了。",
                    "存下的参数回来了：**离边距离** 回到了保存时的值。",
                    "带星标的预设成了默认参数：**默认值** 和新建的缝线层都会用它。"
                ],
                "done": "再点一次星标，默认值就恢复成插件自带的。"
            }
        },
        "grid": "格纹",
        "along": "沿边偏移",
        "angle": "角度",
        "cell": "格子大小",
        "pickInList": "在列表里点选",
        "clickLayer": "在列表里点一个图层",
        "stop": "不再引用",
        "length": "长度",
        "gap": "间隔",
        "bake": "烘焙遮罩",
        "model": "模型",
        "live": "实时更新",
        "rebuild": "刷新",
        "keyEdges": "这一层的边",
        "keyOut": "去掉的边",
        "keyCorners": "尖角",
        "keySel": "选中的边",
        "presetName": "下摆缝线",
        "preDefault": "默认值",
        "preStar": "设为默认",
        "preName": "预设名称",
        "presets": "缝线预设",
        "showCorners": "显示尖角",
        "style": "样式",
        "dashed": "虚线",
        "zigzag": "锯齿",
        "height": "高度",
        "bakeHead": "烘焙",
        "background": "背景",
        "black": "黑底",
        "transparent": "透明",
        "bake1": "烘焙 1 层遮罩",
        "bakeN": "烘焙 {} 层遮罩",
        "object": "物体",
        "material": "材质"
    },
    "ja": {
        "stitches": "Stitches",
        "lineArt": "Line Art",
        "auto": "Auto",
        "fromEdge": "From Edge",
        "width": "Width",
        "none": "None",
        "add": "追加",
        "remove": "外す",
        "select": "選択",
        "clear": "消去",
        "pick": "スポイト",
        "showEdges": "辺を表示",
        "visible": "表示とベイク",
        "skip": "このステップを飛ばす",
        "restart": "最初から",
        "edges": "Edges",
        "reference": "Reference",
        "corners": "Sharp Corners",
        "flip": "Flip Side",
        "demos": {
            "flow": {
                "steps": [
                    "リスト右の **+** を押して **Stitches** を選びます。",
                    "裾のスカラップを 4 つクリックし、**Edges** 行の **+** を押します。",
                    "**From Edge** を 6 mm までドラッグします。",
                    "**Bake 1 Mask** を押します。"
                ],
                "results": [
                    "リストに **Stitches** レイヤーができ、その下に設定が出ました。",
                    "裾がこのレイヤーの辺（緑）になり、ステッチがそれに沿います。",
                    "ステッチは裾から {from} 内側にあります。モデル上で測った距離です。",
                    "最初のマスクができました。黒地に白いステッチが、UV のとおりに並んでいます。"
                ],
                "done": "左上のタブで、モデルとマスクを切り替えられます。"
            },
            "list": {
                "steps": [
                    "**Stitches** の行の目のアイコンを押します。"
                ],
                "results": [
                    "ステッチが非表示になりました。ベイクでも飛ばされます。"
                ],
                "done": "もう一度押すと表示が戻ります。"
            },
            "edges": {
                "steps": [
                    "スカラップを 4 つクリックし、**Edges** 行の **+** を押します。",
                    "スカラップを 1 つクリックして **−** を押します。"
                ],
                "results": [
                    "裾がこのレイヤーの辺（緑）になり、ステッチがそれに沿って走ります。",
                    "そのスカラップはこのレイヤーの辺ではなくなり、ステッチが両端で途切れました。"
                ],
                "done": "**×** で辺を消したり、矢印で選び直したりしてみてください。"
            },
            "reference": {
                "steps": [
                    "**Edges** 行の端のリンクアイコンを押し、**Stitches** を選びます。",
                    "いちばん左のスカラップをクリックし、**Edges** 行の **−** を押します。"
                ],
                "results": [
                    "**Line Art** が **Stitches** の辺をすべて使うようになり、裾はマークし直さなくても緑になりました。新しい **Reference** 行に参照先が表示されます。",
                    "いちばん左のスカラップが赤くなりました。**Line Art** では使いませんが、**Stitches** には残っています。"
                ],
                "done": "リストの **Stitches** を押してみてください。辺はそのままです。"
            },
            "corners": {
                "steps": [
                    "**Sharp Corners** 行の **Auto** を押します。",
                    "2 つ目のスカラップをクリックし、**Sharp Corners** 行の **−** を押します。"
                ],
                "results": [
                    "すべてのスカラップの先がマークされ（黄色）、ステッチはそこで鋭く曲がります。",
                    "両端の先のマークが外れ、ステッチはそこを丸く回り込みます。"
                ],
                "done": "同じ行の **+** で、もう一度マークできます。"
            },
            "flip": {
                "steps": [
                    "**Flip Side** にチェックを入れます。"
                ],
                "results": [
                    "腰の線が辺の上側に移りました。裾の線は布の外に出ています。縁の外側には何もないからです。"
                ],
                "done": "チェックを外すと線が戻ります。"
            },
            "lineart": {
                "steps": [
                    "**From Edge** を 3 mm までドラッグします。",
                    "**Width** を 5 mm までドラッグします。"
                ],
                "results": [
                    "線が裾から {from} 内側へ移りました。**From Edge** は線の外側までの距離です。",
                    "縁取りが幅 {width} の帯になりました。幅はどこも同じで、マークした先はシャープなままです。"
                ],
                "done": "**From Edge** を 0 に戻すと、帯が辺にぴったり付きます。"
            },
            "grid": {
                "steps": [
                    "**Angle** を 45° までドラッグします。",
                    "**Along Edge** か **From Edge** をドラッグします。"
                ],
                "results": [
                    "チェックが {angle} 回りました。起点はマークしたウエストのままです。",
                    "チェックがウエストに沿って、または下へずれます。大きさは変わりません。"
                ],
                "done": "**Cell Size** も動かしてみてください。"
            },
            "style": {
                "steps": [
                    "**Style** を **Zigzag** に切り替えます。",
                    "**Height** を 6 mm までドラッグします。",
                    "**From Edge** を 5 mm までドラッグします。"
                ],
                "results": [
                    "1 本の糸が行き来するステッチになり、パネルの **Gap** が **Height** に変わりました。",
                    "ジグザグの振れ幅が {height} になり、山が裾に届きました。",
                    "線全体が {from} の位置まで内側に移り、山が布の上に戻りました。"
                ],
                "done": "**Dashed** に戻して比べてみてください。"
            },
            "bakeall": {
                "steps": [
                    "**Bake 3 Masks** を押します。",
                    "上のオブジェクト名かマテリアル名を変えてみます。"
                ],
                "results": [
                    "ファイルが 4 つできました。レイヤーごとに 1 枚、Grid は濃いマスと薄いマスの 2 枚です。左上のファイル名を押すと中身が見られます。",
                    "ファイル名も変わりました。もう一度ベイクすると、同じ名前のファイルは上書きされます。"
                ],
                "done": "**Background** を **Transparent** にしてみてください。黒地の代わりに、形が透明度として保存されます。"
            },
            "presets": {
                "steps": [
                    "**Stitches** の横のプリセットボタンを開き、**+** で保存します。",
                    "**From Edge** を別の値にしてから、保存したプリセットを押します。",
                    "プリセットに星を付けてから、**Default** を押します。"
                ],
                "results": [
                    "今の設定がその名前で保存されました。",
                    "保存した設定に戻りました。**From Edge** も保存したときの値です。",
                    "星付きのプリセットが初期値になりました。**Default** と新しいステッチレイヤーにこの設定が使われます。"
                ],
                "done": "もう一度星を押すと、アドオン本来の初期値に戻ります。"
            }
        },
        "grid": "Grid",
        "along": "Along Edge",
        "angle": "Angle",
        "cell": "Cell Size",
        "pickInList": "Pick in List",
        "clickLayer": "Click a layer in the list",
        "stop": "参照をやめる",
        "length": "Length",
        "gap": "Gap",
        "bake": "Bake Masks",
        "model": "モデル",
        "live": "Live Update",
        "rebuild": "Update",
        "keyEdges": "このレイヤーの辺",
        "keyOut": "外した辺",
        "keyCorners": "尖った角",
        "keySel": "選択中の辺",
        "presetName": "裾のステッチ",
        "preDefault": "Default",
        "preStar": "初期値にする",
        "preName": "プリセット名",
        "presets": "Stitch Presets",
        "showCorners": "Show Corners",
        "style": "Style",
        "dashed": "Dashed",
        "zigzag": "Zigzag",
        "height": "Height",
        "bakeHead": "Bake",
        "background": "Background",
        "black": "Black",
        "transparent": "Transparent",
        "bake1": "Bake 1 Mask",
        "bakeN": "Bake {} Masks",
        "object": "オブジェクト",
        "material": "マテリアル"
    }
}

# theme: follow the system until the reader picks one; the pick is kept in
# localStorage and applied in <head>, before the page draws
THEME_HEAD = ("(function(){var d=document.documentElement,t=null;try{t=localStorage.getItem('pm-theme')}catch(e){}"
              "if(t)d.dataset.theme=t;var m=matchMedia('(prefers-color-scheme: dark)');"
              "function s(){var k=d.dataset.theme?d.dataset.theme==='dark':m.matches;"
              "if(k)d.setAttribute('data-dark','');else d.removeAttribute('data-dark')}s();"
              "m.addEventListener('change',s);window.pmToggleTheme=function(){"
              "var k=d.hasAttribute('data-dark');d.dataset.theme=k?'light':'dark';"
              "try{localStorage.setItem('pm-theme',d.dataset.theme)}catch(e){}s()}})()")

FIG_IMG = {
    "fig-hero-render": ("render.png", "dark", ""),
    "fig-panel": ("panel.png", "", ""),
    "fig-reference": ("reference.svg", "", "reference_note"),
    "fig-masks": ("uv_masks.png", "dark", ""),
}


# -- a small Markdown subset: paragraphs, lists, bold, italics, code, links -----
def inline(text):
    out = []
    for i, part in enumerate(re.split(r"(`[^`]+`)", text)):
        if i % 2:
            out.append("<code>" + html.escape(part[1:-1]).replace("_", "_<wbr>") + "</code>")
            continue
        t = html.escape(part, quote=False)
        t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"<em>\1</em>", t)
        out.append(t)
    return "".join(out)


def markdown(md):
    """Paragraphs, lists, "### " subheads and "> " notes. A list whose every item
    starts with bold names and a colon ("**+**: adds ...") becomes a list of
    controls: the names in one column, what they do in the other."""
    blocks, cur, kind = [], [], None
    key_re = re.compile(r"(\*\*.+?\*\*(?:\s*[、,/]\s*\*\*.+?\*\*)*)\s*[：:]\s*(.+)")

    def flush():
        nonlocal cur, kind
        if not cur:
            return
        if kind == "p":
            blocks.append("<p>" + inline(" ".join(cur)) + "</p>")
        elif kind == "note":
            blocks.append('<p class="note">' + inline(" ".join(cur)) + "</p>")
        elif kind == "ul" and all(key_re.fullmatch(i) for i in cur):
            rows = "".join(f"<dt>{inline(m.group(1))}</dt><dd>{inline(m.group(2))}</dd>"
                           for m in (key_re.fullmatch(i) for i in cur))
            blocks.append(f'<dl class="keys">{rows}</dl>')
        else:
            tag = "ol" if kind == "ol" else "ul"
            blocks.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in cur) + f"</{tag}>")
        cur, kind = [], None

    for line in md.replace("\r", "").split("\n"):
        s = line.strip()
        if not s:
            flush()
            continue
        m_ol = re.match(r"\d+[.)]\s+(.*)", s)
        m_ul = re.match(r"[-*]\s+(.*)", s)
        if s.startswith("### "):
            flush()
            blocks.append("<h3>" + inline(s[4:]) + "</h3>")
        elif s.startswith("> "):
            if kind != "note":
                flush()
                kind = "note"
            cur.append(s[2:])
        elif m_ol or m_ul:
            k = "ol" if m_ol else "ul"
            if kind != k:
                flush()
                kind = k
            cur.append((m_ol or m_ul).group(1))
        elif kind in ("ol", "ul") and line.startswith((" ", "\t")):
            cur[-1] += " " + s
        else:
            if kind != "p":
                flush()
                kind = "p"
            cur.append(s)
    flush()
    return "\n".join(blocks)


# -- replica settings panels ------------------------------------------------------
# The rows of the add-on's panel, in its order and with its defaults (see
# VIEW3D_PT_stitch_gen.draw). (row id, kind, value, shown for style); a None
# starts a new group. Labels and words come from the section's "keys".
REF_ROWS = {
    "stitch": [("from", "num", "3 mm"), ("corner_inset", "num", "0 mm"), ("smooth", "num", "2 mm"), None,
               ("style", "enum", ["dash", "zigzag"]), None,
               ("width", "num", "1.2 mm"), ("length", "num", "4 mm"), ("gap", "num", "2 mm", "dash"),
               ("round", "slider", "1.000", "dash"), ("height", "num", "3 mm", "zigzag"), None,
               ("even", "check", True, "dash")],
    "line": [("from", "num", "0 mm"), ("corner_inset", "num", "0 mm"), ("smooth", "num", "0 mm"), None,
             ("width", "num", "0.5 mm")],
    "grid": [("from", "num", "0 mm"), ("along", "num", "0 mm"), None,
             ("angle", "num", "0°"), ("cell", "num", "8 mm"), ("wobble", "slider", "0.300"), None,
             ("layout", "enum", ["loops", "unrolled"])],
    "bake": [("size", "menu", "4096"), ("uv", "menu", "uv_active"), ("folder", "path", "//stitch_masks/"),
             ("background", "enum", ["black", "transparent"]), None, ("samples", "sub", "")],
}
# values shown inside the replica (the add-on's own words; it has no Japanese)
REF_VALUES = {
    "en": {"dash": "Dashed", "zigzag": "Zigzag", "loops": "Follow Loops", "unrolled": "Unrolled",
           "black": "Black", "transparent": "Transparent", "uv_active": "Active: UVMap"},
    "zh-CN": {"dash": "虚线", "zigzag": "锯齿", "loops": "顺布线", "unrolled": "展开",
              "black": "黑底", "transparent": "透明", "uv_active": "当前：UVMap"},
}


def refpanel(kind, lang, keys=None):
    """Replica of one settings block: the panel on the left, each row's words on
    the right, row by row. Only Style and Layout can be switched."""
    vals = REF_VALUES.get(lang, REF_VALUES["en"])
    words = {k: (label, desc) for k, label, desc in (keys or [])}
    rows, first = [], True
    for spec in REF_ROWS[kind]:
        if spec is None:
            rows.append('<div class="rp-gap"></div>')
            continue
        rid, typ, val = spec[:3]
        show = f' data-show="{spec[3]}"' if len(spec) > 3 else ""
        label, desc = words.get(rid, (rid, ""))
        label = label.replace("**", "")
        if typ == "num" or typ == "path" or typ == "menu":
            v = vals.get(val, val) if typ == "menu" else val
            arrow = '<i class="dd"></i>' if typ == "menu" else ""
            ctl = f'<span class="rp-field{" path" if typ == "path" else ""}">{html.escape(v)}{arrow}</span>'
        elif typ == "slider":
            ctl = f'<span class="rp-field slider" style="--f:{float(val) * 100:.0f}%">{html.escape(val)}</span>'
        elif typ == "enum":
            ctl = ('<span class="rp-seg">' + "".join(
                f'<button type="button" data-v="{o}"{" class=on" if i == 0 else ""}>{html.escape(vals[o])}</button>'
                for i, o in enumerate(val)) + "</span>")
        elif typ == "check":
            ctl = f'<span class="rp-check"><i class="on"></i>{html.escape(label)}</span>'
        else:                                           # a closed sub-panel
            ctl = f'<span class="rp-sub">{html.escape(label)}</span>'
        lab = "" if typ in ("check", "sub") else html.escape(label)
        rows.append(f'<div class="rp-row" data-r="{rid}"{show}><div class="rp-ui"><span class="rp-lb">{lab}</span>{ctl}</div>'
                    f'<div class="rp-desc">{inline(desc)}</div></div>')
    return f'<figure class="fig refpanel" data-ref="{kind}">' + "".join(rows) + '</figure>'


# -- figures --------------------------------------------------------------------
def figure(fid, lang):
    ui = UI[lang]
    if fid in FIG_IMG:
        name, cls, note = FIG_IMG[fid]
        cap = f"<figcaption>{html.escape(ui[note])}</figcaption>" if note else ""
        return f'<figure class="fig {cls}"><img src="../img/{name}" alt="" loading="lazy">{cap}</figure>'
    if fid == "fig-grid-layouts":       # each render says what it shows, under it
        cap = lambda k: (f'<figcaption><strong>{html.escape(ui[k])}</strong>'
                         f'<span>{inline(ui[k + "_note"])}</span></figcaption>')
        return (f'<figure class="fig pair dark">'
                f'<div><img src="../img/grid_loops.png" alt="" loading="lazy">{cap("loops")}</div>'
                f'<div><img src="../img/grid_unrolled.png" alt="" loading="lazy">{cap("unrolled")}</div>'
                f'</figure>')
    if fid.startswith("sb-"):
        demo = fid[3:]
        words = {k: v for k, v in PRACTICE[lang].items() if k != "demos"}
        data = html.escape(json.dumps(dict(words, demo=demo, **PRACTICE[lang]["demos"][demo]), ensure_ascii=False), quote=True)
        return f'<figure class="fig practice mini" id="demo-{demo}" data-sandbox="{data}"></figure>'
    if fid == "fig-install":           # the sidebar of the real add-on, its tab marked
        return ('<figure class="fig shot" id="shot-install"><div class="shot-box">'
                '<img src="../img/sidebar.png" alt="" width="310" height="390" loading="lazy">'
                '<span class="hs" data-hs="tab" style="left:92%;top:61%;width:8%;height:25%"></span>'
                '<span class="hs" data-hs="panel" style="left:1%;top:0;width:90%;height:100%"></span>'
                '</div></figure>')
    if fid.startswith("ref-"):
        return refpanel(fid[4:], lang)
    if fid == "fig-workflow":
        steps = "".join(f'<li><img src="../img/step{i + 1}.svg" alt=""><span>{i + 1}. {html.escape(t)}</span></li>'
                        for i, t in enumerate(ui["workflow"]))
        return f'<figure class="fig workflow"><ol>{steps}</ol></figure>'
    return ""


# -- pages ----------------------------------------------------------------------
CSS = "../style.css"


GROUPS = [("g_start", ["index", "start"]),
          ("g_ideas", ["layers", "stitches", "line-art", "grid", "presets", "bake"]),
          ("g_ref", ["limits"])]


# "on this page": mark the section being read
TOC_SPY = ("(function(){var l=[].slice.call(document.querySelectorAll('.toc a'));if(!l.length)return;"
           "var s=l.map(function(a){return document.getElementById(decodeURIComponent(a.hash.slice(1)))});"
           "function u(){var n=0;for(var i=0;i<s.length;i++)if(s[i]&&s[i].getBoundingClientRect().top<=150)n=i;"
           "if(scrollY>0&&innerHeight+scrollY>=document.documentElement.scrollHeight-4)n=s.length-1;"
           "l.forEach(function(a,i){a.classList.toggle('now',i===n)})}"
           "addEventListener('scroll',u,{passive:true});addEventListener('resize',u);u()})()")


def nav(pages, lang, slug):
    by = {p["slug"]: p for p in pages}
    out = []
    for key, slugs in GROUPS:
        items = []
        for sl in slugs:
            if sl not in by:
                continue
            cls = ' class="here"' if sl == slug else ""
            href = "index.html" if sl == "index" else f"{sl}.html"
            items.append(f'<li><a{cls} href="{href}">{html.escape(by[sl]["title"])}</a></li>')
        out.append(f'<p class="grp">{html.escape(UI[lang][key])}</p><ol>' + "".join(items) + "</ol>")
    return "".join(out)


def page_html(pages, i, lang):
    ui = UI[lang]
    p = pages[i]
    fname = "index.html" if p["slug"] == "index" else f'{p["slug"]}.html'
    langs = "".join(
        f'<a href="../{code}/{fname}"{" aria-current=page" if code == lang else ""}>{name}</a>'
        for code, name in LANGS)
    toc = "".join(f'<li><a href="#{s["id"]}">{html.escape(s["heading"])}</a></li>' for s in p["sections"])
    body = []
    flow = []                                     # Start: the steps beside one demo

    def section(s, fig_id):
        step = f' data-step="{s["step"]}"' if "step" in s else ""
        part = [f'<section id="{s["id"]}"{step}><h2>{html.escape(s["heading"])}</h2>',
                markdown(s.get("body", ""))]
        if s.get("table"):
            rows = "".join(f"<tr><th>{inline(a)}</th><td>{inline(b)}</td></tr>" for a, b in s["table"])
            part.append(f'<table class="settings">{rows}</table>')
        fid = s.get("figure", "")
        if fid.startswith("ref-"):
            part.append(refpanel(fid[4:], lang, s.get("keys")))
        elif fid and "step" not in s:
            part.append(figure(fid, lang))
        if s.get("keys") and not fid.startswith("ref-"):      # numbered to match its figure's controls
            target = fig_id or ("demo-" + fid[3:] if fid.startswith("sb-") else "shot-install" if fid == "fig-install" else "")
            part.append(f'<ol class="um-keys" data-for="{target}">' + "".join(
                f'<li data-t="{html.escape(t)}"><span class="um-n">{i}</span><span class="um-k">{inline(k)}</span>'
                f'<span class="um-d">{inline(d)}</span></li>' for i, (t, k, d) in enumerate(s["keys"], 1)) + "</ol>")
        part.append("</section>")
        return "\n".join(part)

    def close_flow():
        if flow:
            fid = flow[0]["figure"]
            body.append('<div class="flow"><div class="flow-text">' + "".join(section(x, "demo-" + fid[3:]) for x in flow)
                        + f'</div><div class="flow-demo">{figure(fid, lang)}</div></div>')
            flow.clear()

    for s in p["sections"]:
        if "step" in s:
            flow.append(s)
            continue
        close_flow()
        body.append(section(s, ""))
    close_flow()

    def link(j, label):
        if not 0 <= j < len(pages):
            return "<span></span>"
        q = pages[j]
        href = "index.html" if q["slug"] == "index" else f'{q["slug"]}.html'
        return f'<a href="{href}"><small>{label}</small>{html.escape(q["title"])}</a>'

    extra_js = ('\n<script src="../practice.js"></script>'
                if any(x.get("figure", "").startswith(("sb-", "ref-", "fig-install"))
                       for x in p["sections"]) else "")
    title = "Pattern Masks" if p["slug"] == "index" else f'{p["title"]} · Pattern Masks'
    return f'''<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="icon" href="../img/icon-small.svg">
<link rel="stylesheet" href="{CSS}">
<script>{THEME_HEAD}</script>
</head>
<body>
<header class="top">
  <a class="brand" href="index.html"><img src="../img/icon-small.svg" alt=""><span>Pattern Masks</span><small>{ui["docs"]}</small></a>
  <nav class="langs" aria-label="{ui["lang"]}">{langs}</nav>
  <a class="repo" href="{REPO_URL}">{ui["repo"]}</a>
  <button class="theme" type="button" aria-label="{ui["theme"]}" title="{ui["theme"]}" onclick="pmToggleTheme()">
    <!-- moon and sun: Lucide 0.460.0 (lucide.dev), ISC License, (c) Lucide Contributors -->
    <svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>
    <svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2m-7.07-17.07 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>
  </button>
</header>
<div class="wrap{" wide" if any("step" in x for x in p["sections"]) else ""}">
  <nav class="side" aria-label="{ui["menu"]}"><button class="side-toggle" type="button" aria-expanded="false"
    onclick="var n=this.parentNode;n.classList.toggle('open');this.setAttribute('aria-expanded',n.classList.contains('open'))">{html.escape(p["title"])}</button>{nav(pages, lang, p["slug"])}</nav>
  <main>
    <h1>{html.escape(p["title"])}</h1>
    <p class="lead">{inline(p.get("lead", ""))}</p>
    {"".join(body)}
    <nav class="pager">{link(i - 1, ui["prev"])}{link(i + 1, ui["next"])}</nav>
  </main>
  <aside class="toc"><p>{ui["on_page"]}</p><ol>{toc}</ol></aside>
</div>
{extra_js}
<script>{TOC_SPY}</script>
</body>
</html>
'''


def main():
    os.makedirs(SITE, exist_ok=True)
    for code, _ in LANGS:
        path = os.path.join(CONTENT, f"{code}.json")
        if not os.path.exists(path):
            print("missing", path)
            continue
        pages = json.load(open(path, encoding="utf-8"))["pages"]
        out = os.path.join(SITE, code)
        os.makedirs(out, exist_ok=True)
        for i, p in enumerate(pages):
            name = "index.html" if p["slug"] == "index" else f'{p["slug"]}.html'
            with open(os.path.join(out, name), "w", encoding="utf-8") as f:
                f.write(page_html(pages, i, code))
        print("built", code, len(pages), "pages")
    # the root picks a language
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write("""<!doctype html><html><head><meta charset="utf-8"><title>Pattern Masks</title>
<script>
var l = (navigator.language || "en").toLowerCase();
location.replace(l.startsWith("zh") ? "zh-CN/" : l.startsWith("ja") ? "ja/" : "en/");
</script></head><body><a href="en/">English</a> · <a href="zh-CN/">简体中文</a> · <a href="ja/">日本語</a></body></html>
""")
    shutil.copy(os.path.join(HERE, "site_style.css"), os.path.join(SITE, "style.css"))
    shutil.copy(os.path.join(HERE, "site_practice.js"), os.path.join(SITE, "practice.js"))
    open(os.path.join(SITE, ".nojekyll"), "w").close()


if __name__ == "__main__":
    main()
