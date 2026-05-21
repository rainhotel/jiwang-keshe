"""生成网络拓扑图 (使用matplotlib + networkx)"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
import os

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 输出路径
OUTPUT = os.path.join(os.path.dirname(__file__), "images", "topology.png")


def draw_topology():
    fig, ax = plt.subplots(1, 1, figsize=(16, 10))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.set_title("校园智慧网络拓扑图", fontsize=18, fontweight="bold", pad=20)

    # === 定义节点坐标 ===
    # 区域框
    areas = {
        "教学区\nVLAN 10": (2, 2),
        "办公区\nVLAN 20": (5, 2),
        "图书馆\nVLAN 30": (8, 2),
        "学生宿舍\nVLAN 40": (11, 2),
        "管理区\nVLAN 60": (14, 2),
    }

    # 核心设备
    core_pos = (7.5, 5.5)
    router_pos = (7.5, 7.5)

    # 服务器区
    server_area = (13, 5.5)

    # === 绘制区域框 ===
    for label, (x, y) in areas.items():
        rect = mpatches.FancyBboxPatch(
            (x - 1, y - 0.4), 2, 1.2,
            boxstyle="round,pad=0.1",
            facecolor="#E3F2FD", edgecolor="#1565C0", linewidth=1.5
        )
        ax.add_patch(rect)
        ax.text(x, y + 0.55, label.split("\n")[0], ha="center", va="bottom",
                fontsize=8, fontweight="bold", color="#0D47A1")
        ax.text(x, y + 0.25, label.split("\n")[1], ha="center", va="bottom",
                fontsize=7, color="#1565C0")

    # === 绘制服务器区框 ===
    server_rect = mpatches.FancyBboxPatch(
        (11.5, 4.5), 3, 3.5,
        boxstyle="round,pad=0.1",
        facecolor="#FFF3E0", edgecolor="#E65100", linewidth=1.5
    )
    ax.add_patch(server_rect)
    ax.text(13, 7.5, "服务器区 VLAN 50", ha="center", va="center",
            fontsize=8, fontweight="bold", color="#BF360C")

    # 服务器节点
    servers = [
        ("DNS\n192.168.50.2", 12.2, 6.8),
        ("WWW\n192.168.50.3", 13, 6.8),
        ("FTP\n192.168.50.4", 13.8, 6.8),
        ("MAIL\n192.168.50.5", 13.2, 5.8),
    ]
    for label, sx, sy in servers:
        ax.plot(sx, sy, "s", markersize=14, color="#FF7043", markeredgecolor="#BF360C")
        ax.text(sx, sy - 0.3, label, ha="center", va="top", fontsize=6, color="#BF360C")

    # === 绘制核心交换机 ===
    ax.plot(core_pos[0], core_pos[1], "D", markersize=28, color="#2E7D32",
            markeredgecolor="#1B5E20", markeredgewidth=2, zorder=5)
    ax.text(core_pos[0], core_pos[1], "核心交换机\nL3 Switch\n10.0.0.1",
            ha="center", va="center", fontsize=7, color="white", fontweight="bold", zorder=6)

    # === 绘制汇聚交换机 ===
    agg1_pos = (3.5, 3.8)
    agg2_pos = (11, 3.8)
    ax.plot(agg1_pos[0], agg1_pos[1], "D", markersize=20, color="#43A047",
            markeredgecolor="#2E7D32", markeredgewidth=1.5, zorder=5)
    ax.text(agg1_pos[0], agg1_pos[1], "接入交换机1", ha="center", va="center",
            fontsize=6, color="white", fontweight="bold", zorder=6)

    ax.plot(agg2_pos[0], agg2_pos[1], "D", markersize=20, color="#43A047",
            markeredgecolor="#2E7D32", markeredgewidth=1.5, zorder=5)
    ax.text(agg2_pos[0], agg2_pos[1], "接入交换机2", ha="center", va="center",
            fontsize=6, color="white", fontweight="bold", zorder=6)

    # === 绘制路由器 ===
    ax.plot(router_pos[0], router_pos[1], "D", markersize=24, color="#F4511E",
            markeredgecolor="#BF360C", markeredgewidth=2, zorder=5)
    ax.text(router_pos[0], router_pos[1], "路由器\nNAT+ACL\n10.0.0.2",
            ha="center", va="center", fontsize=6, color="white", fontweight="bold", zorder=6)

    # 外网云
    internet_rect = mpatches.FancyBboxPatch(
        (6.5, 8.0), 2, 0.8,
        boxstyle="round,pad=0.1",
        facecolor="#ECEFF1", edgecolor="#78909C", linewidth=1
    )
    ax.add_patch(internet_rect)
    ax.text(7.5, 8.4, "Internet / ISP", ha="center", va="center",
            fontsize=8, fontweight="bold", color="#455A64")

    # === 绘制连线 ===
    # 核心到路由器
    ax.plot([core_pos[0], router_pos[0]], [core_pos[1] + 0.3, router_pos[1] - 0.3],
            "k-", linewidth=2, zorder=2)
    ax.text(6.8, 6.5, "10.0.0.0/30", fontsize=6, color="#333", rotation=90, va="center")

    # 路由器到外网
    ax.plot([router_pos[0], 7.5], [router_pos[1] + 0.3, 8.0],
            "k-", linewidth=2, zorder=2)
    ax.text(7.5, 7.75, "203.0.113.1/24", fontsize=6, color="#333", va="center")

    # 核心到汇聚交换机
    ax.plot([core_pos[0] - 0.3, core_pos[0] - 0.3], [core_pos[1] - 0.3, agg1_pos[1] + 0.3],
            "lightcoral", linewidth=1.5, linestyle="--", zorder=2)
    ax.text(6.8, 4.6, "Trunk", fontsize=6, color="#D32F2F", fontstyle="italic")

    ax.plot([core_pos[0] + 0.3, core_pos[0] + 0.3], [core_pos[1] - 0.3, agg2_pos[1] + 0.3],
            "lightcoral", linewidth=1.5, linestyle="--", zorder=2)
    ax.text(8.0, 4.6, "Trunk", fontsize=6, color="#D32F2F", fontstyle="italic")

    # 汇聚到区域
    for label, (x, y) in areas.items():
        if x < 7:
            ax.plot([agg1_pos[0], x], [agg1_pos[1], y + 0.6],
                    "k-", linewidth=1, alpha=0.5, zorder=1)
        else:
            ax.plot([agg2_pos[0], x], [agg2_pos[1], y + 0.6],
                    "k-", linewidth=1, alpha=0.5, zorder=1)

    # 接入交换机2到服务器区
    ax.plot([agg2_pos[0], 13], [agg2_pos[1], 4.5],
            "k-", linewidth=1, alpha=0.5, zorder=1)

    # === 图例 ===
    legend_elements = [
        mpatches.Patch(facecolor="#E3F2FD", edgecolor="#1565C0", label="终端区域"),
        mpatches.Patch(facecolor="#FFF3E0", edgecolor="#E65100", label="服务器区"),
        plt.Line2D([0], [0], marker="D", color="w", markerfacecolor="#2E7D32",
                   markersize=10, label="核心层设备"),
        plt.Line2D([0], [0], marker="D", color="w", markerfacecolor="#43A047",
                   markersize=8, label="汇聚层设备"),
        plt.Line2D([0], [0], marker="D", color="w", markerfacecolor="#F4511E",
                   markersize=8, label="路由器"),
    ]
    ax.legend(handles=legend_elements, loc="lower center", ncol=5,
              fontsize=7, framealpha=0.8, bbox_to_anchor=(0.5, -0.04))

    plt.tight_layout()
    plt.savefig(OUTPUT, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"拓扑图已保存至: {OUTPUT}")


if __name__ == "__main__":
    draw_topology()
