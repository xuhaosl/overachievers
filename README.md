# 学生成绩助手（studentassistant）

家庭自用的孩子成绩管理工具，部署在自己的 NAS / 服务器上，手机电脑浏览器都能用。

## 功能

- **孩子管理**：登记孩子信息，一键升年级（新成绩自动记录当时的年级）
- **学科管理**：自定义学科、颜色、默认总分；每个学科可管理自己的单元（一键生成"第1~N单元"）
- **录成绩**：
  - 「录一条」：单元测试等单科成绩，选学科、选单元、填分数
  - 「考试场次」：期中/期末等全科考试，先建场次再逐科录分，可录全科总分的年级/班级排名
  - 支持附加分（显示为"85（10）"：常规分＋括号内附加分）、年级排名、班级排名（名次/总人数），都可选填
  - 年级、学期自动推断（按日期），可手动修改
- **成绩列表**：按孩子/学科/类型/年级/学期/时间筛选，可编辑删除
- **曲线**：
  - 单科得分率曲线（可多科同图对比，悬浮显示原始分数）
  - 总分曲线（按场次聚合，得分率统一量纲）
  - 单科排名曲线 / 总分排名曲线（名次越小越高，可切换年级/班级）
  - 时间范围：本学期 / 本学年 / 全部 / 自定义

## 数据说明

- 数据存在 **一个 SQLite 文件** 里（容器内 `/app/data/studentassistant.db`），备份 = 复制 `data` 目录
- 所有数据保存在你自己的 NAS 上，不经过任何第三方

## Docker 部署

### 方式一：docker-compose（推荐）

```bash
git clone https://github.com/<你的用户名>/studentassistant.git
cd studentassistant
docker compose up -d --build
```

浏览器打开 `http://<NAS的IP>:8100` 即可使用。

### 方式二：极空间 NAS 图形界面

极空间 ZOS 的 Docker 应用支持两种方式：

1. **Compose 一键部署**（新版本支持）：Docker → Compose → 新建，粘贴 `docker-compose.yml` 的内容，启动
2. **本地镜像导入**：
   - 在电脑上执行 `docker build -t studentassistant:latest .`，再 `docker save -o studentassistant.tar studentassistant:latest`
   - 把 `studentassistant.tar` 拷进极空间，Docker → 镜像 → 本地导入
   - 用该镜像创建容器：
     - 端口映射：`8100 -> 8100`
     - 文件夹映射：在极空间个人空间建一个 `studentassistant` 文件夹，映射到容器 `/app/data`
     - 环境变量（可选）：`APP_PASSWORD=你的密码`、`TZ=Asia/Shanghai`

### 访问密码（可选）

默认局域网内无需登录。若要把服务暴露到公网，设置环境变量 `APP_PASSWORD`（或 `docker-compose.yml` 旁放 `.env` 文件），打开页面时会先要求输入密码。

## 本地开发

```bash
# 后端（端口 8100）
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8100

# 前端（端口 5173，已配置代理到 8100）
cd frontend
npm install
npm run dev
```

## 技术栈

后端 Python FastAPI + SQLite；前端 Vue3 + Element Plus + ECharts；单 Docker 容器部署。

## License

[MIT](LICENSE)
