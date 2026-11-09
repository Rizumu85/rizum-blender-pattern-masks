"""Hand-written UI translations (Simplified Chinese).

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
    "The stitch row stays; hide it with its eye": "缝线这一行不能删除，可以点眼睛隐藏",
    "Add the selected edges to the layer selected in the list": "把选中的边加到列表里选中的那一层",
    "Remove the selected edges from the layer selected in the list":
        "把选中的边从列表里选中的那一层移除",
    "Select the edges of the layer selected in the list": "选中列表里选中那一层的边",
    "Clear all edges of the layer selected in the list": "清空列表里选中那一层的全部边",
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
    "Extra inset at marked corners, tapering off along the line, for a deeper, pointed corner":
        "在尖角处额外往里缩，并沿缝线逐渐过渡回来，让拐角更深更尖",
    "Flip Side": "翻到另一侧",
    "Round Ends": "圆角",
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
    "Distance of the stitch line from the picked edges": "缝线离所选边的距离",
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
    "Add the stitches; while they are selected, the edge buttons mark their edges":
        "添加缝线；选中它时，边按钮标的就是缝线的边",
    "The object already has stitches": "这个物体已经有缝线了",
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
    "White with the mask in the alpha channel (soft edges kept), for Clip Studio and other 2D apps":
        "白色，遮罩在 alpha 通道里（保留柔边），CSP 等 2D 软件用这种",
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
    "Slides the squares away from the marked edge": "让方格离开标记的边整体滑动",
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
    "Bake Mask": "烘焙遮罩",
    "Detect Corners": "自动识别尖角",
    "Transparent Background": "透明背景",
    "Save white stitches on a transparent background (the stitch is the alpha), e.g. for Clip Studio. Off: white on black, as Painter masks expect":
        "保存成透明背景上的白色缝线（缝线就是 alpha），方便在 CSP 等软件里用；关闭时是黑底白线，Painter 遮罩用这种",
    "Select Corners": "选择尖角",
    "Select the vertices marked as corners": "选中已标记为尖角的顶点",
    "Marked {} corners": "已标记 {} 个尖角",
    "Mark Corner": "标记尖角",
    "Clear Corner": "取消尖角",
    "Include Stitch Edges": "包含缝线边",
    "Smooths the inner side of the line between corners, like the stitch line; the outer side keeps the exact edge":
        "像缝线一样平滑线的内侧（尖角处保持尖），外侧仍然贴着边",
    "Also follow the stitch edges, not only the line art edges": "除了线稿边，也沿缝线边画线",
    "Rebuild the stitches": "重新生成缝线",
    "Bake the stitches into a 16-bit mask PNG per texture set":
        "把缝线烘焙成遮罩，每个纹理集一张 16 位 PNG",

    # line art
    "Stitches": "缝线",
    "Stitch Color": "缝线颜色",
    "Color of the stitch preview in the viewport (not baked)": "视图里缝线预览的颜色（不影响烘焙）",
    "Width of the line, the same real size everywhere": "线的宽度，在模型上处处是同样的实际尺寸",
    "Distance from the picked edges to the outer side of the line (0 = the line starts at the edge)":
        "从所选边到线外侧的距离（0 = 线从边上开始）",
    "Extra inset at marked corners, tapering off along the edge, for a deeper, pointed corner":
        "在尖角处额外往里缩，并沿边逐渐过渡回来，让拐角更深更尖",
    "Used in the file name of this layer's mask": "用在这一层遮罩的文件名里",
    "Add Line": "添加线稿",
    "Remove Line": "删除线稿",
    "Remove the selected line art layer": "删除选中的线稿层",
    "Bake Masks": "烘焙遮罩",
    "Bake the stitches and each line art layer into a 16-bit mask PNG per texture set":
        "把缝线和每层线稿烘焙成遮罩，每个纹理集各一张 16 位 PNG",

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
    "Grid": "格纹",
    "Along Edge": "沿边偏移",
    "Cell Size": "格子大小",
    "Angle": "角度",
    "Wobble": "扭曲",
    "Layout": "排法",
    "Follow Loops": "顺布线",
    "Unrolled": "展开",
    "Stitches: Samples & Device": "缝线：采样与设备",
    "Default": "默认值",
    "Style": "样式",
    "Dashed": "虚线",
    "Zigzag": "锯齿",
    "Height": "高度",
    "Line Art": "线稿",
    "Stitches": "缝线",
    "Line": "线稿",           # default name of a line art layer
    "Background": "背景",
    "Black": "黑底",
    "Transparent": "透明",
    "Smooth": "平滑",
    "Corner Inset": "尖角内缩",
    "Length": "长度",
    "Gap": "间隔",
    "Width": "宽度",
    "From Edge": "离边距离",
}

OPERATOR_NAMES = ("Add Selected", "Remove Selected", "Select Edges", "Clear Edges",
                  "Update", "Bake Mask", "Mark Corner", "Clear Corner", "Detect Corners",
                  "Select Corners", "Add Line", "Remove Line", "Bake Masks", "Add Stitches",
                  "Remove Layer", "Apply Preset", "Use as Default")

translations = {
    "zh_HANS": {
        **{("*", k): v for k, v in ZH.items()},
        **{("Operator", k): ZH[k] for k in OPERATOR_NAMES},
        **{(CTX, k): v for k, v in ZH_CTX.items()},
    },
}


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
