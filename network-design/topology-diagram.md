# 网络拓扑详细描述（Packet Tracer 搭建参考）

## 设备清单

| 设备           | 型号建议          | 数量 | 用途                               |
|---------------|-------------------|------|-----------------------------------|
| 三层交换机     | Cisco 3560-24PS   | 1    | 核心交换机，VLAN间路由、DHCP           |
| 二层交换机     | Cisco 2960-24TT   | 2    | 汇聚/接入层                           |
| 路由器         | Cisco 1941        | 1    | 出口路由器，NAT、ACL                   |
| 服务器         | Server-PT         | 4    | DNS、WWW、FTP、MAIL                  |
| PC终端         | PC-PT             | 10+  | 各区域终端                            |
| 直连线         | Copper Straight   | 若干  | 设备互联                              |
| 交叉线         | Copper Cross-Over | 若干  | 交换机间互联（如需）                   |

## 设备互联表

| 源设备      | 源端口        | 目标设备        | 目标端口        |
|------------|---------------|-----------------|-----------------|
| Core-Switch| G0/1          | Access-Switch1  | G0/1            |
| Core-Switch| G0/2          | Access-Switch2  | G0/1            |
| Core-Switch| G0/24         | Edge-Router     | G0/0            |
| Edge-Router| G0/1          | ISP-Cloud       | -               |
| Access-Switch1 | F0/1-12  | PC-Jiaoxue      | F0              |
| Access-Switch1 | F0/13-24 | PC-Bangong      | F0              |
| Access-Switch2 | F0/1-6   | PC-Tushuguan    | F0              |
| Access-Switch2 | F0/7-14  | PC-Sushe        | F0              |
| Access-Switch2 | F0/15-18 | Servers         | F0              |
| Access-Switch2 | F0/19-24 | PC-Guanli       | F0              |

## 搭建步骤

1. 放置设备：按拓扑图拖入所有设备
2. 连接线缆：按互联表使用直连线连接各设备
3. 交换机-交换机间用Trunk链路（交叉线）
4. 核心交换机和路由器间用直连线
5. 配置各设备IP（参考 configs/ 目录下各配置文件）
6. 完成各区域的简单测试（ping、DHCP获取、Web访问等）
