import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Create figure canvas
fig, ax = plt.subplots(figsize=(10, 14), dpi=300)
ax.set_xlim(0, 100)
ax.set_ylim(0, 140)
ax.axis("off")
fig.patch.set_facecolor("#F8F9FA")

# Box Drawing Helper
def draw_card(y_top, height, title, items, color, border_color):
    # Background Box
    rect = patches.FancyBboxPatch(
        (5, y_top - height),
        90,
        height,
        boxstyle="round,pad=1",
        linewidth=2,
        edgecolor=border_color,
        facecolor=color,
    )
    ax.add_patch(rect)
    # Title
    ax.text(
        10,
        y_top - 6,
        title,
        fontsize=12,
        weight="bold",
        color=border_color,
    )
    # List Items
    for i, item in enumerate(items):
        ax.text(
            12,
            y_top - 14 - (i * 6),
            f"• {item}",
            fontsize=10,
            color="#2D3748",
        )


# Draw Arrows
def draw_arrow(y_start, y_end):
    ax.annotate(
        "",
        xy=(50, y_end),
        xytext=(50, y_start),
        arrowprops=dict(
            arrowstyle="->", lw=2, color="#4A5568", mutation_scale=15
        ),
    )


# Title Header
ax.text(
    50,
    135,
    "FindMyPath.ai V3 — App Workflow Blueprint",
    fontsize=16,
    weight="bold",
    ha="center",
    color="#1A202C",
)

# 1. Screen 1 Card
draw_card(
    128,
    28,
    "SCREEN 1: INTAKE ASSESSMENT (IMAGE 2)",
    [
        "Drag & Drop 6 Work Values Cards (Security, Freedom, etc.)",
        "Drag & Drop 6 RIASEC Archetypes ('Builder', 'Researcher', etc.)",
        "Generates unambiguous ordinal ranking (Eliminates ties)",
        "User Clicks 'NEXT'",
    ],
    "#EBF3FF",
    "#2B6CB0",
)

draw_arrow(98, 93)

# 2. Backend Engine Card
draw_card(
    92,
    22,
    "BACKEND ENGINE: MAPPING LAYER",
    [
        "Converts ranking into 3-Letter Holland Code (e.g., I-S-A)",
        "Maps Holland Code to Class 11 Academic Streams",
        "Filters Science (PCM/PCB), Commerce, and Humanities rules",
    ],
    "#FFF5F5",
    "#C53030",
)

draw_arrow(68, 63)

# 3. Screen 2 Card
draw_card(
    62,
    26,
    "SCREEN 2: STREAM GUIDANCE RESULTS (IMAGE 1)",
    [
        "Renders visual Holland Interest Curve Graph (R-I-A-S-E-C)",
        "Highlights Top Interest Badges",
        "Displays Stream Cards with non-prescriptive explanations",
        "User Clicks 'Explore Activities'",
    ],
    "#F0FFF4",
    "#276749",
)

draw_arrow(34, 29)

# 4. Screen 3 Card
draw_card(
    28,
    22,
    "SCREEN 3: ACTIVITY & SKILL MODAL (IMAGES 3 & 4)",
    [
        "Presents checklist of Detailed Work Activities",
        "Student checks preferred daily activities",
        "Refines subject electives, entrance exams, & bridge courses",
    ],
    "#FFFFF0",
    "#B7791F",
)

# Save image as JPG
plt.tight_layout()
plt.savefig("findmypath_v3_workflow.jpg", format="jpg", bbox_inches="tight")
print("Workflow diagram saved successfully as 'findmypath_v3_workflow.jpg'!")
