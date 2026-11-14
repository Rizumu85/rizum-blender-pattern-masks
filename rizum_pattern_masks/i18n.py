"""Hand-written UI translations (Simplified Chinese, Japanese).

Blender looks strings up by (context, message). Property names, panel titles
and tooltips use the default context "*"; operator names use "Operator".
Messages with values are translated as templates, then formatted.
"""

import bpy

ZH = {
    # panel and layer list
    "Rizum Pattern Masks": "Rizum 图案遮罩",
    "Pattern Masks": "图案遮罩",
    "Sharp Corners": "尖角",
    "Edges": "边",
    "Show Edges": "显示标记的边",
    "Show this layer's marked edges in the viewport (display only)":
        "在视图里显示这一层标记的边（只是显示）",
    "Show Corners": "显示尖角",
    "Show the marked corners in the viewport (display only)": "在视图里显示标记的尖角（只是显示）",
    "Color of this layer's preview in the viewport (not baked)":
        "这一层在视图里预览的颜色（不影响烘焙）",
    "Show and bake this layer": "显示并烘焙这一层",
    "Show and bake the stitches": "显示并烘焙缝线",
    "Select Edges": "选择边",
    "Clear Edges": "清空边",
    "Works in Edit Mode": "在编辑模式下使用",
    "Edit the mesh, not its preview": "请编辑模型本身，不是它的预览",
    "No edges selected": "没有选中的边",
    "Choose Folder": "选择文件夹",
    "Choose the folder for the mask PNGs": "选择保存遮罩 PNG 的文件夹",
    "Keep the folder relative to the .blend file": "按相对 .blend 文件的路径保存",
    "Clear All Layers": "清空所有图层",
    "Remove all layers, with their marked edges and corners, and the previews from every object in the scene":
        "删除场景里所有物体的图层，连同标记的边、尖角和预览",
    "Remove all layers, marked edges, corners and previews from every object in this scene?":
        "删除这个场景里所有物体的图层、标记的边、尖角和预览？",
    "Clear": "清空",
    "Nothing to clear": "没有可以清空的内容",
    "Cleared {} objects": "已清空 {} 个物体",
    "Show Marks": "显示标记",
    "Show the marked edges and corners of all layers in the viewport (display only)":
        "在视图里显示所有图层标记的边和尖角（只影响显示）",
    "The marked edges are too short for a stitch": "标记的边太短，放不下一针",
    "Add the selected edges to the layer selected in the list": "把选中的边加到列表里选中的那一层",
    "Remove the selected edges from the layer selected in the list, also those it gets from the layer it refers to":
        "把选中的边从列表里选中的那一层移除，引用来的边也可以去掉",
    "Select the edges of the layer selected in the list, with those it gets from the layer it refers to":
        "选中列表里选中那一层的边，包括引用来的边",
    "Clear all edges of the layer selected in the list, and bring back the edges it took out of its reference":
        "清空列表里选中那一层的全部边，去掉的引用边也恢复",
    "Keep the lines sharp at the selected vertices": "让线在所选顶点处保持尖角",
    "Let the lines round off at the selected vertices again": "所选顶点处的线恢复圆滑",
    "Mark likely corners on the marked edges automatically (replaces the marks there)":
        "在标记的边上自动标出可能的尖角（会替换那里原有的标记）",
    "Add a line art layer; while it is selected, the edge buttons mark its edges":
        "添加一层线稿；选中它时，边按钮标的就是它的边",

    # panel and tab
    "Bake": "烘焙",

    # settings
    "Live": "实时更新",
    "Flip Side": "翻到另一侧",
    "Round Ends": "圆角",
    "Corner radius of each stitch: 100% gives fully round ends": "每针两端的圆角，100% 是完全圆头",
    "How far the stitch line sits inward from the marked edges": "缝线从标记的边向内偏移多少",
    "How far the line sits inward from the marked edges, to its outer side (0 = the line starts at the edge)":
        "线稿从标记的边向内偏移多少，量到线的外侧（0 = 线从边上开始）",
    "Extra inward offset at marked corners, tapering off along the line, for a deeper, pointed corner":
        "在标记的尖角处再向内多偏移这么多，沿线逐渐减小，让尖角更深更尖",
    "Slides the squares inward from the marked edge": "让方格从标记的边向内整体滑动",
    "Even Fit": "均匀排布",
    "Size": "尺寸",
    "UV Map": "UV 贴图",
    "Folder": "文件夹",
    "Samples": "采样",
    "Device": "设备",
    "CPU Usage": "CPU 占用",
    "What bakes. GPU is faster but can make the screen stutter while baking":
        "用什么烘焙。GPU 更快，但烘焙时画面可能卡顿",
    "Share of CPU cores the bake may use; the rest keeps Blender responsive":
        "烘焙可以使用的 CPU 核心比例，剩下的留给 Blender 保持流畅",
    "Baking {}/{}": "烘焙中 {}/{}",
    "Unrolling {}/{}": "展开中 {}/{}",
    "Baking stopped": "烘焙已停止",

    # tooltips of the settings
    "Rebuild the stitches while you change the values": "改数值时自动重新生成缝线",
    "Evens out low-poly zigzags along the line; larger values also flatten curves":
        "抹平低模边上的折线；数值越大，弧线也会被拉平",
    "Inset to the other side of the picked edges": "向所选边的另一侧内缩",
    "Space between stitches": "针脚之间的空隙",
    "Thread width": "线的宽度",
    "Corner radius of each stitch as a fraction of half its width (1 = fully round ends)":
        "针脚两端的圆角，按半宽的比例（1 为全圆头）",
    "Slide the stitches along the line": "让针脚沿缝线整体滑动",
    "Closed loops get a whole number of stitches; open lines get equal space at both ends":
        "闭合环上的针脚数取整；开口的线两端留空相等",
    "Size of the baked mask PNGs, in pixels": "烘焙出的遮罩 PNG 的尺寸（像素）",
    "UV map to bake into; empty follows the mesh's active UV map":
        "烘焙用的 UV 贴图；没有指定时跟随网格当前激活的 UV 贴图",
    "Active: {}": "当前：{}",
    "Follow Active UV Map": "跟随当前 UV 贴图",
    "Set this layer's settings back to the default: the starred preset, or the add-on's own":
        "把这一层的参数恢复成默认值：标了星的预设，没有的话用插件自带的",
    "Apply Preset": "套用预设",
    "Apply this preset": "套用这个预设",
    "Use as Default": "设为默认",
    "Use this preset as the default: new layers start with it, and Default applies it. Click again to go back to the add-on's own default":
        "把这个预设设为默认：新建的层用它的参数，点“默认值”也会套用它。再点一次就恢复成插件自带的默认值",
    "Separate stitches along the line": "沿线一段一段的针脚",
    "One thread going back and forth across the line": "一根线沿着缝线来回走成锯齿",
    "Kind of stitch": "针脚的样式",
    "How far the zigzag swings across the line, from peak to peak": "锯齿左右摆动的幅度（从一边尖到另一边尖）",
    "Length of each stitch; for a zigzag, the distance along the line from one peak to the next":
        "每个针脚的长度；锯齿时是沿缝线从一个尖到下一个尖的距离",
    "Add Layer": "添加图层",
    "Add Stitches": "添加缝线",
    "Add a stitch layer; while it is selected, the edge buttons mark its edges":
        "添加一层缝线；选中它时，边按钮标的就是它的边",
    "Remove Layer": "删除图层",
    "Remove the selected layer together with its marked edges": "删除选中的图层和它标记的边",
    "Name of this layer; a name you type also goes into the file name of its mask":
        "这一层的名字；自己起的名字也会用在遮罩的文件名里",
    "Preview color in the viewport (not baked)": "视图里的预览颜色（不影响烘焙）",
    "Bake 1 Mask": "烘焙 1 层遮罩",
    "Bake {} Masks": "烘焙 {} 层遮罩",
    "Open Folder": "打开文件夹",
    "Open the mask folder in the file manager": "在资源管理器里打开遮罩文件夹",
    "Nothing baked here yet": "这里还没有烘焙过",
    "Nothing to bake: show a layer that has edges": "没有可烘焙的内容：请显示一个标了边的层",
    "White on black, as Painter masks expect": "黑底白遮罩，Painter 用这种",
    "Black on white. In Clip Studio Paint, Convert Brightness to Opacity turns it into a mask (it can't open a transparent PNG that holds very little)":
        "白底黑遮罩。在 Clip Studio Paint 里用「将亮度转换为透明度」就能变成遮罩（内容很少的透明 PNG 它导入不了）",
    "Save black stitches on white (used when Transparent is off)": "保存成白底黑缝线（不透明时生效）",
    "White Background": "白底",
    "White with the mask in the alpha channel (soft edges kept), for Photoshop and other 2D apps":
        "白色，遮罩在 alpha 通道里（保留柔边），Photoshop 等 2D 软件用这种",
    "Background of the saved mask PNGs": "保存的遮罩 PNG 的背景",
    "Stitch Presets": "缝线预设",
    "Grid Presets": "格纹预设",
    "Add Grid": "添加格纹",
    "Add Grid Preset": "添加格纹预设",
    "Add a checkered layer: squares that follow the mesh's loops out from a marked edge":
        "添加一层格纹：从标记的边出发，方格顺着网格的布线排",
    "Turns the squares against the marked edge (45 degrees: on the bias)":
        "让方格相对标记的边转个角度（45° 就是斜裁）",
    "Save this grid layer's settings as a preset, or remove the selected preset":
        "把这层格纹的参数存成预设，或删除选中的预设",
    "Slides the squares along the marked edge": "让方格沿标记的边整体滑动",
    "Size of each square": "每个方格的大小",
    "Bends the lines of the squares a little at random, as cloth pulls them out of true; the corners stay sharp":
        "让格子的线随机地轻轻弯曲，像布料被拉扯后那样；四个角仍然是尖的",
    "The squares follow the mesh's loops out from the marked edge, forking where the piece widens":
        "方格从标记的边出发顺着网格的布线排，衣片变宽的地方会分叉",
    "The piece unrolled on its marked edge: the edge straight, the columns straight down from it, and the squares square but growing where the piece widens; nothing forks":
        "把衣片沿标记的边展开：边是直的，列从边上垂直往下，方格保持正方形但随衣片变宽而变大；不分叉",
    "Line Art Presets": "线稿预设",
    "Add Stitch Preset": "添加缝线预设",
    "Add Line Art Preset": "添加线稿预设",
    "Save the stitch settings as a preset, or remove the selected preset":
        "把缝线参数存成预设，或删除选中的预设",
    "Save this line art layer's settings as a preset, or remove the selected preset":
        "把这层线稿的参数存成预设，或删除选中的预设",
    "Auto": "自动",
    "Bake into this UV map": "烘焙到这个 UV 贴图",
    "Set UV Map": "设置 UV 贴图",
    "Folder for the mask PNGs; baking again overwrites them": "遮罩 PNG 的保存位置；再次烘焙会覆盖",
    "Bake samples per texel": "每个纹素的烘焙采样数",

    # operators (name + tooltip)
    "Add Selected": "添加所选边",
    "Remove Selected": "移除所选边",
    "Update": "重新生成",
    "Detect Corners": "自动识别尖角",
    "Transparent Background": "透明背景",
    "Save white stitches on a transparent background (the stitch is the alpha), e.g. for Clip Studio. Off: white on black, as Painter masks expect":
        "保存成透明背景上的白色缝线（缝线就是 alpha），方便在 CSP 等软件里用；关闭时是黑底白线，Painter 遮罩用这种",
    "Select Corners": "选择尖角",
    "Select the vertices marked as corners": "选中已标记为尖角的顶点",
    "Marked {} corners": "已标记 {} 个尖角",
    "Mark Corner": "标记尖角",
    "Clear Corner": "取消尖角",
    "Smooths the inner side of the line between corners, like the stitch line; the outer side keeps the exact edge":
        "像缝线一样平滑线的内侧（尖角处保持尖），外侧仍然贴着边",
    "Reference": "引用",
    "Also follow this layer's edges": "也沿这个图层的边走",
    "Pick Layer": "吸取图层",
    "Pick in List": "在列表里点选",
    "Click a layer in the list": "在列表里点一个图层",
    "Also follows {}": "也沿「{}」的边走",
    "Clear Reference": "取消引用",
    "Also follow another layer's edges": "也沿另一个图层的边走",
    "Stop following that layer's edges": "不再沿那个图层的边走",
    "Click a layer in the list to also follow its edges (Esc or right-click: cancel)":
        "在列表里点一个图层，也沿它的边走（Esc 或右键取消）",
    "Rebuild the stitches": "重新生成缝线",

    # line art
    "Stitches": "缝线",
    "Stitch Color": "缝线颜色",
    "Color of the stitch preview in the viewport (not baked)": "视图里缝线预览的颜色（不影响烘焙）",
    "Width of the line, the same real size everywhere": "线的宽度，在模型上处处是同样的实际尺寸",
    "Used in the file name of this layer's mask": "用在这一层遮罩的文件名里",
    "Add Line": "添加线稿",
    "Bake Masks": "烘焙遮罩",
    "Bake the stitches and each line art layer into a 16-bit mask PNG per texture set, for every selected object":
        "把缝线和每层线稿烘焙成遮罩，每个纹理集各一张 16 位 PNG；选中的物体都会烘焙",

    # messages (templates)
    "{count} stitches: Length + Gap too small for this path (limit {limit})":
        "{count} 个针脚：针脚长度加间隔对这条路径太小（上限 {limit}）",
    "Saved {}": "已保存 {}",
    'The mesh already has an attribute "{}" of another type; rename it first':
        '网格上已有另一种类型的属性 "{}"，请先改名',
    "No stitches to bake": "没有可以烘焙的缝线",
    "Save the .blend file first, or pick an absolute output folder":
        "请先保存 .blend 文件，或选择一个绝对路径的输出文件夹",
    "{} has no UV map": "{} 没有 UV 贴图",
    "{} is open in another program (for example Clip Studio Paint or Painter) and can't be replaced. Close it there and bake again":
        "{} 正被其他软件占用（比如 Clip Studio Paint 或 Painter），没法覆盖。请在那边关掉这个文件后再烘焙",
}

# Lengths (shown with mm in the field) use their own context.
CTX = "StitchGen"
ZH_CTX = {
    "Offset Inward": "向内偏移",
    "Corner Depth": "尖角加深",
    "Offset Along": "沿边偏移",
    "Grid": "格纹",
    "Cell Size": "格子大小",
    "Angle": "角度",
    "Wobble": "扭曲",
    "Layout": "排法",
    "Follow Loops": "顺布线",
    "Unrolled": "展开",
    "Stitches: Samples & Device": "缝线：采样与设备",
    "Default": "默认值",
    "Reference": "引用",
    "Style": "样式",
    "Dashed": "虚线",
    "Zigzag": "锯齿",
    "Height": "高度",
    "Line Art": "线稿",
    "Stitches": "缝线",
    "Line": "线稿",           # default name of a line art layer
    "Background": "背景",
    "Black": "黑底",
    "White": "白底",
    "Transparent": "透明",
    "Smooth": "平滑",
    "Length": "长度",
    "Gap": "间隔",
    "Width": "宽度",
}

# Japanese: the words of the Japanese docs (ステッチ, 線画, チェック柄, マーク)
JA = {
    # panel and layer list
    "Rizum Pattern Masks": "Rizum パターンマスク",
    "Pattern Masks": "パターンマスク",
    "Sharp Corners": "尖った角",
    "Edges": "辺",
    "Show Edges": "マークした辺を表示",
    "Show this layer's marked edges in the viewport (display only)":
        "このレイヤーのマークした辺をビューポートに表示します（表示のみ）",
    "Show Corners": "角を表示",
    "Show the marked corners in the viewport (display only)": "マークした角をビューポートに表示します（表示のみ）",
    "Color of this layer's preview in the viewport (not baked)":
        "ビューポートでのこのレイヤーのプレビュー色（ベイクには影響しません）",
    "Show and bake this layer": "このレイヤーを表示してベイクします",
    "Show and bake the stitches": "ステッチを表示してベイクします",
    "Select Edges": "辺を選択",
    "Clear Edges": "辺をクリア",
    "Works in Edit Mode": "編集モードで使えます",
    "Edit the mesh, not its preview": "プレビューではなくメッシュ本体を編集してください",
    "No edges selected": "辺が選択されていません",
    "Choose Folder": "フォルダーを選択",
    "Choose the folder for the mask PNGs": "マスク PNG の保存先フォルダーを選びます",
    "Keep the folder relative to the .blend file": ".blend ファイルからの相対パスで保存します",
    "Clear All Layers": "すべてのレイヤーをクリア",
    "Remove all layers, with their marked edges and corners, and the previews from every object in the scene":
        "シーン内のすべてのオブジェクトから、レイヤーとそのマークした辺・角、プレビューを削除します",
    "Remove all layers, marked edges, corners and previews from every object in this scene?":
        "このシーンのすべてのオブジェクトから、レイヤー、マークした辺と角、プレビューを削除しますか？",
    "Clear": "クリア",
    "Nothing to clear": "クリアするものがありません",
    "Cleared {} objects": "{} 個のオブジェクトをクリアしました",
    "Show Marks": "マークを表示",
    "Show the marked edges and corners of all layers in the viewport (display only)":
        "すべてのレイヤーのマークした辺と角をビューポートに表示します（表示のみ）",
    "The marked edges are too short for a stitch": "マークした辺が短すぎて、ステッチが入りません",
    "Add the selected edges to the layer selected in the list": "選択した辺を、リストで選んだレイヤーに追加します",
    "Remove the selected edges from the layer selected in the list, also those it gets from the layer it refers to":
        "選択した辺を、リストで選んだレイヤーから外します。参照先から来た辺も外せます",
    "Select the edges of the layer selected in the list, with those it gets from the layer it refers to":
        "リストで選んだレイヤーの辺を、参照先から来た辺も含めて選択します",
    "Clear all edges of the layer selected in the list, and bring back the edges it took out of its reference":
        "リストで選んだレイヤーの辺をすべてクリアし、参照から外した辺も元に戻します",
    "Keep the lines sharp at the selected vertices": "選択した頂点で線を尖らせたままにします",
    "Let the lines round off at the selected vertices again": "選択した頂点で、線がまた丸く回り込むようにします",
    "Mark likely corners on the marked edges automatically (replaces the marks there)":
        "マークした辺の上で角らしい所を自動でマークします（そこにあるマークは置き換わります）",
    "Add a line art layer; while it is selected, the edge buttons mark its edges":
        "線画レイヤーを追加します。選択中は、辺のボタンでこのレイヤーの辺をマークします",

    # panel and tab
    "Bake": "ベイク",

    # settings
    "Live": "自動更新",
    "Flip Side": "反対側",
    "Round Ends": "端の丸み",
    "Corner radius of each stitch: 100% gives fully round ends": "ステッチ端の丸み。100% で完全な丸になります",
    "How far the stitch line sits inward from the marked edges": "マークした辺から、ステッチの線をどれだけ内側に入れるか",
    "How far the line sits inward from the marked edges, to its outer side (0 = the line starts at the edge)":
        "マークした辺から線の外側までを、どれだけ内側に入れるか（0 = 線は辺から始まります）",
    "Extra inward offset at marked corners, tapering off along the line, for a deeper, pointed corner":
        "マークした角でさらに内側へ入れる量。線に沿って次第に小さくなり、角がより深く尖ります",
    "Slides the squares inward from the marked edge": "マス目を、マークした辺から内側へずらします",
    "Even Fit": "均等に配置",
    "Size": "サイズ",
    "UV Map": "UV マップ",
    "Folder": "フォルダー",
    "Samples": "サンプル数",
    "Device": "デバイス",
    "CPU Usage": "CPU 使用率",
    "What bakes. GPU is faster but can make the screen stutter while baking":
        "ベイクに使うデバイス。GPU は速いですが、ベイク中に画面がカクつくことがあります",
    "Share of CPU cores the bake may use; the rest keeps Blender responsive":
        "ベイクに使える CPU コアの割合。残りは Blender の操作用に空けておきます",
    "Baking {}/{}": "ベイク中 {}/{}",
    "Unrolling {}/{}": "展開中 {}/{}",
    "Baking stopped": "ベイクを中止しました",

    # tooltips of the settings
    "Rebuild the stitches while you change the values": "値を変えるたびにステッチを作り直します",
    "Evens out low-poly zigzags along the line; larger values also flatten curves":
        "ローポリの辺のガタつきを線に沿ってならします。値を大きくすると曲線も平らになります",
    "Inset to the other side of the picked edges": "選んだ辺の反対側に入れます",
    "Space between stitches": "ステッチ同士の間隔",
    "Thread width": "糸の太さ",
    "Corner radius of each stitch as a fraction of half its width (1 = fully round ends)":
        "ステッチ端の丸み。半幅に対する割合（1 = 完全な丸）",
    "Slide the stitches along the line": "ステッチを線に沿ってずらします",
    "Closed loops get a whole number of stitches; open lines get equal space at both ends":
        "閉じたループではステッチ数を整数にそろえ、開いた線では両端の余白を等しくします",
    "Size of the baked mask PNGs, in pixels": "ベイクするマスク PNG のサイズ（ピクセル）",
    "UV map to bake into; empty follows the mesh's active UV map":
        "ベイク先の UV マップ。空欄ならメッシュのアクティブな UV マップに従います",
    "Active: {}": "現在：{}",
    "Follow Active UV Map": "アクティブな UV マップに従う",
    "Set this layer's settings back to the default: the starred preset, or the add-on's own":
        "このレイヤーの設定をデフォルトに戻します。星を付けたプリセット、なければアドオン既定の値です",
    "Apply Preset": "プリセットを適用",
    "Apply this preset": "このプリセットを適用します",
    "Use as Default": "デフォルトにする",
    "Use this preset as the default: new layers start with it, and Default applies it. Click again to go back to the add-on's own default":
        "このプリセットをデフォルトにします。新しいレイヤーはこの設定で始まり、「デフォルト」でもこれが適用されます。もう一度押すとアドオン既定の値に戻ります",
    "Separate stitches along the line": "線に沿って一針ずつ並ぶステッチ",
    "One thread going back and forth across the line": "1 本の糸が線をまたいで行き来するジグザグ",
    "Kind of stitch": "ステッチの種類",
    "How far the zigzag swings across the line, from peak to peak": "ジグザグの振れ幅（山から反対側の山まで）",
    "Length of each stitch; for a zigzag, the distance along the line from one peak to the next":
        "1 針の長さ。ジグザグでは、線に沿って山から次の山までの距離",
    "Add Layer": "レイヤーを追加",
    "Add Stitches": "ステッチを追加",
    "Add a stitch layer; while it is selected, the edge buttons mark its edges":
        "ステッチのレイヤーを追加します。選択中は、辺のボタンでこのレイヤーの辺をマークします",
    "Remove Layer": "レイヤーを削除",
    "Remove the selected layer together with its marked edges": "選択したレイヤーを、マークした辺ごと削除します",
    "Name of this layer; a name you type also goes into the file name of its mask":
        "このレイヤーの名前。入力した名前はマスクのファイル名にも使われます",
    "Preview color in the viewport (not baked)": "ビューポートでのプレビュー色（ベイクには影響しません）",
    "Bake 1 Mask": "マスクを 1 枚ベイク",
    "Bake {} Masks": "マスクを {} 枚ベイク",
    "Open Folder": "フォルダーを開く",
    "Open the mask folder in the file manager": "マスクのフォルダーをファイルマネージャーで開きます",
    "Nothing baked here yet": "まだここにはベイクしていません",
    "Nothing to bake: show a layer that has edges": "ベイクするものがありません。辺をマークしたレイヤーを表示してください",
    "White on black, as Painter masks expect": "黒地に白。Painter のマスクはこの形式です",
    "Black on white. In Clip Studio Paint, Convert Brightness to Opacity turns it into a mask (it can't open a transparent PNG that holds very little)":
        "白地に黒。CLIP STUDIO PAINT では「輝度を透明度に変換」でマスクになります（中身の少ない透明 PNG は読み込めないため）",
    "Save black stitches on white (used when Transparent is off)": "白地に黒いステッチで保存します（透明がオフのとき）",
    "White Background": "白背景",
    "White with the mask in the alpha channel (soft edges kept), for Photoshop and other 2D apps":
        "白で、マスクはアルファチャンネルに入ります（ぼかしも保持）。Photoshop などの 2D ソフト向け",
    "Background of the saved mask PNGs": "保存するマスク PNG の背景",
    "Stitch Presets": "ステッチのプリセット",
    "Grid Presets": "チェック柄のプリセット",
    "Add Grid": "チェック柄を追加",
    "Add Grid Preset": "チェック柄のプリセットを追加",
    "Add a checkered layer: squares that follow the mesh's loops out from a marked edge":
        "チェック柄のレイヤーを追加します。マス目はマークした辺から、メッシュのループに沿って並びます",
    "Turns the squares against the marked edge (45 degrees: on the bias)":
        "マス目をマークした辺に対して回します（45° でバイアス）",
    "Save this grid layer's settings as a preset, or remove the selected preset":
        "このチェック柄レイヤーの設定をプリセットとして保存するか、選択中のプリセットを削除します",
    "Slides the squares along the marked edge": "マス目を、マークした辺に沿ってずらします",
    "Size of each square": "1 マスの大きさ",
    "Bends the lines of the squares a little at random, as cloth pulls them out of true; the corners stay sharp":
        "布に引っ張られたように、マス目の線をランダムに少し曲げます。角は尖ったままです",
    "The squares follow the mesh's loops out from the marked edge, forking where the piece widens":
        "マス目はマークした辺からメッシュのループに沿って並び、パーツが広がる所で分かれます",
    "The piece unrolled on its marked edge: the edge straight, the columns straight down from it, and the squares square but growing where the piece widens; nothing forks":
        "パーツをマークした辺で展開します。辺はまっすぐ、列は辺からまっすぐ下に伸び、マス目は正方形のままパーツが広がる所で大きくなります。分かれません",
    "Line Art Presets": "線画のプリセット",
    "Add Stitch Preset": "ステッチのプリセットを追加",
    "Add Line Art Preset": "線画のプリセットを追加",
    "Save the stitch settings as a preset, or remove the selected preset":
        "ステッチの設定をプリセットとして保存するか、選択中のプリセットを削除します",
    "Save this line art layer's settings as a preset, or remove the selected preset":
        "この線画レイヤーの設定をプリセットとして保存するか、選択中のプリセットを削除します",
    "Auto": "自動",
    "Bake into this UV map": "この UV マップにベイクします",
    "Set UV Map": "UV マップを設定",
    "Folder for the mask PNGs; baking again overwrites them": "マスク PNG の保存先。もう一度ベイクすると上書きされます",
    "Bake samples per texel": "テクセルあたりのベイクのサンプル数",

    # operators (name + tooltip)
    "Add Selected": "選択した辺を追加",
    "Remove Selected": "選択した辺を外す",
    "Update": "更新",
    "Detect Corners": "角を自動検出",
    "Transparent Background": "透明背景",
    "Save white stitches on a transparent background (the stitch is the alpha), e.g. for Clip Studio. Off: white on black, as Painter masks expect":
        "透明な背景に白いステッチで保存します（ステッチがアルファ）。CLIP STUDIO などで使えます。オフ：黒地に白で、Painter のマスク用",
    "Select Corners": "角を選択",
    "Select the vertices marked as corners": "角としてマークした頂点を選択します",
    "Marked {} corners": "{} 個の角をマークしました",
    "Mark Corner": "角をマーク",
    "Clear Corner": "角のマークを解除",
    "Smooths the inner side of the line between corners, like the stitch line; the outer side keeps the exact edge":
        "ステッチの線と同じように、角と角の間で線の内側をなめらかにします。外側は辺にぴったり沿ったままです",
    "Reference": "参照",
    "Also follow this layer's edges": "このレイヤーの辺にも沿います",
    "Pick Layer": "スポイトで選ぶ",
    "Pick in List": "リストから選ぶ",
    "Click a layer in the list": "リストのレイヤーをクリックしてください",
    "Also follows {}": "「{}」の辺にも沿っています",
    "Clear Reference": "参照を解除",
    "Also follow another layer's edges": "別のレイヤーの辺にも沿います",
    "Stop following that layer's edges": "そのレイヤーの辺に沿うのをやめます",
    "Click a layer in the list to also follow its edges (Esc or right-click: cancel)":
        "リストのレイヤーをクリックすると、その辺にも沿います（Esc か右クリックで取り消し）",
    "Rebuild the stitches": "ステッチを作り直します",

    # line art
    "Stitches": "ステッチ",
    "Stitch Color": "ステッチの色",
    "Color of the stitch preview in the viewport (not baked)": "ビューポートでのステッチのプレビュー色（ベイクには影響しません）",
    "Width of the line, the same real size everywhere": "線の太さ。モデル上のどこでも同じ実寸です",
    "Used in the file name of this layer's mask": "このレイヤーのマスクのファイル名に使われます",
    "Add Line": "線画を追加",
    "Bake Masks": "マスクをベイク",
    "Bake the stitches and each line art layer into a 16-bit mask PNG per texture set, for every selected object":
        "ステッチと各線画レイヤーを、テクスチャセットごとに 16 ビットのマスク PNG にベイクします。選択中のオブジェクトすべてが対象です",

    # messages (templates)
    "{count} stitches: Length + Gap too small for this path (limit {limit})":
        "ステッチ {count} 個：この線には長さ＋間隔が小さすぎます（上限 {limit}）",
    "Saved {}": "{} を保存しました",
    'The mesh already has an attribute "{}" of another type; rename it first':
        "メッシュに型の違う属性「{}」がすでにあります。先に名前を変えてください",
    "No stitches to bake": "ベイクするステッチがありません",
    "Save the .blend file first, or pick an absolute output folder":
        "先に .blend ファイルを保存するか、絶対パスの出力フォルダーを選んでください",
    "{} has no UV map": "{} に UV マップがありません",
    "{} is open in another program (for example Clip Studio Paint or Painter) and can't be replaced. Close it there and bake again":
        "{} は別のソフト（CLIP STUDIO PAINT や Painter など）で開かれているため置き換えられません。そちらで閉じてからもう一度ベイクしてください",
}
JA_CTX = {
    "Offset Inward": "内側オフセット",
    "Corner Depth": "角の深さ",
    "Offset Along": "線方向オフセット",
    "Grid": "チェック柄",
    "Cell Size": "マスの大きさ",
    "Angle": "角度",
    "Wobble": "ゆらぎ",
    "Layout": "並べ方",
    "Follow Loops": "ループに沿う",
    "Unrolled": "展開",
    "Stitches: Samples & Device": "ステッチ：サンプル数とデバイス",
    "Default": "デフォルト",
    "Reference": "参照",
    "Style": "スタイル",
    "Dashed": "破線",
    "Zigzag": "ジグザグ",
    "Height": "高さ",
    "Line Art": "線画",
    "Stitches": "ステッチ",
    "Line": "線画",           # default name of a line art layer
    "Background": "背景",
    "Black": "黒",
    "White": "白",
    "Transparent": "透明",
    "Smooth": "スムーズ",
    "Length": "長さ",
    "Gap": "間隔",
    "Width": "幅",
}

OPERATOR_NAMES = ("Add Selected", "Remove Selected", "Select Edges", "Clear Edges",
                  "Update", "Mark Corner", "Clear Corner", "Detect Corners",
                  "Select Corners", "Add Line", "Bake Masks", "Add Stitches",
                  "Remove Layer", "Apply Preset", "Use as Default",
                  "Reference", "Pick Layer", "Clear All Layers", "Choose Folder")

def _table(words, ctx_words):
    return {**{("*", k): v for k, v in words.items()},
            **{("Operator", k): words[k] for k in OPERATOR_NAMES},
            **{(CTX, k): v for k, v in ctx_words.items()}}


translations = {"zh_HANS": _table(ZH, ZH_CTX), "ja_JP": _table(JA, JA_CTX)}


def iface(msg):
    """Translate an interface string (labels, panel text)."""
    return bpy.app.translations.pgettext_iface(msg)


def rpt(msg):
    """Translate a report / error message."""
    fn = getattr(bpy.app.translations, "pgettext_rpt", None) or bpy.app.translations.pgettext_iface
    return fn(msg)


def register(package):
    bpy.app.translations.register(package, translations)


def unregister(package):
    bpy.app.translations.unregister(package)
