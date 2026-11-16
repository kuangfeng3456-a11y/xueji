# 华为云 RDS / DCS Redis 开通与接入清单

本清单用于在一个**没有现成云资源**的环境中，从零开通「学迹」所需的华为云 RDS MySQL 与 DCS Redis，并把应用切到真实云服务。

> 当前仓库状态：应用侧连接配置、接入中心探活、开通脚本与数据迁移脚本已完成；本机没有华为云凭证与 VPC 参数，真实实例尚未创建。本文档就是补齐这些前置条件的最短路径。

## 1. 需要准备什么

| 项目 | 用途 | 在哪里获取 |
| --- | --- | --- |
| AK / SK | 脚本调用华为云 API | 控制台 → 我的凭证 → 访问密钥 |
| 项目 ID | 指定区域下的资源归属 | 控制台 → 我的凭证 → API 凭证 → 项目列表 |
| 区域 | RDS/DCS 所在地域 | 控制台左上角区域选择器 |
| VPC ID | 实例所在虚拟私有云 | VPC 控制台 → 虚拟私有云 |
| 子网 ID | 实例所在子网 | VPC 控制台 → 子网 |
| 安全组 ID | 控制实例访问规则 | VPC 控制台 → 安全组 |
| DCS 规格编码 | 决定 Redis 规格 | DCS 控制台 → 购买缓存实例 → 规格编码 |

## 2. 控制台操作路径

### 2.1 创建 AK/SK 与项目 ID

1. 登录华为云控制台。
2. 右上角账号名 → **我的凭证**。
3. 左侧 **访问密钥** → **新增访问密钥**，下载 `credentials.csv`（只显示一次）。
4. 左侧 **API 凭证** → **项目列表**，找到目标区域对应的 **项目 ID** 并复制。

> 建议使用 IAM 子用户，而不是主账号 AK/SK。子用户需加入具备 RDS、DCS、VPC 权限的用户组。

### 2.2 确认区域

控制台左上角区域选择器，例如：

- 华北-北京四：`cn-north-4`
- 华东-上海一：`cn-east-3`
- 华南-广州：`cn-south-1`

可用区一般填 `{区域}a`，例如 `cn-north-4a`。脚本默认使用 `{区域}a`。

### 2.3 获取 VPC / 子网 / 安全组 ID

1. 控制台 → **网络** → **虚拟私有云 VPC**。
2. **虚拟私有云** 列表：复制 VPC ID（形如 `vpc-xxxxxxxx`）。
3. **子网** 列表：复制子网 ID（形如 `subnet-xxxxxxxx`）。
4. **安全组** 列表：复制安全组 ID（形如 `sg-xxxxxxxx`）。
5. 进入安全组 → **入方向规则** → 添加规则：
   - MySQL：协议 TCP，端口 `3306`，源地址填你的公网 IP 或同 VPC 网段。
   - Redis：协议 TCP，端口 `6379`，源地址同上。

若没有 VPC，可先在控制台创建：
- VPC 网段建议 `192.168.0.0/16`；
- 子网网段建议 `192.168.1.0/24`；
- 安全组使用默认或新建。

### 2.4 获取 DCS 规格编码

1. 控制台 → **应用中间件** → **分布式缓存服务 DCS**。
2. **购买缓存实例** → 选择 **Redis 5.0** → 容量 **1GB**。
3. 页面会显示 **规格编码 / spec_code**（形如 `redis.ha.xu1.large.r2.1`，不同区域可能不同）。
4. 复制该编码，填入 `DCS_SPEC_CODE`。

> 脚本不会猜规格编码，避免创建出非预期规格。

### 2.5 权限清单

执行开通的 IAM 用户至少需要：

| 服务 | 权限 |
| --- | --- |
| RDS | RDS FullAccess（创建、查询实例与规格） |
| DCS | DCS FullAccess（创建、查询实例） |
| VPC | VPC ReadOnlyAccess（读取已有 VPC/子网/安全组；若需创建 VPC 则要 VPC FullAccess） |
| IAM | 读取项目 ID（通常随账号信息可见） |

账号还需满足：已实名认证、账户余额充足、目标区域 RDS/DCS 配额足够。

## 3. 填写模板

```bash
cd backend
copy .env.cloud.example .env.cloud
notepad .env.cloud
```

模板字段：

```dotenv
HUAWEICLOUD_SDK_AK=
HUAWEICLOUD_SDK_SK=
CLOUD_PROJECT_ID=
CLOUD_REGION=cn-north-4
CLOUD_AVAILABILITY_ZONE=cn-north-4a
CLOUD_VPC_ID=
CLOUD_SUBNET_ID=
CLOUD_SECURITY_GROUP_ID=
RDS_NAME=xueji-mysql
RDS_VOLUME_SIZE=40
RDS_FLAVOR=
RDS_PASSWORD=
DCS_NAME=xueji-redis
DCS_CAPACITY=1
DCS_SPEC_CODE=
DCS_PASSWORD=
```

应用会自动读取 `backend/.env.cloud`，无需手动合并到 `.env`。该文件已被 `.gitignore` 忽略。

## 4. 执行开通

```bash
cd backend

# 1. 检查参数，不创建资源
python scripts/provision_cloud.py --dry-run

# 2. 真实创建 RDS MySQL 8.0 单机 + DCS Redis（会产生费用）
python scripts/provision_cloud.py --apply

# 3. 输出连接信息到 .env.cloud 的 RDS_* / REDIS_* 变量
#    脚本会等待实例可用并打印连接地址
```

> RDS 创建通常需要 5–15 分钟，DCS 约 5–10 分钟。脚本默认最多等待 30 分钟，可用 `--timeout` 调整。

## 5. 迁移数据

```bash
# 查看源库各表行数，不写目标
python scripts/migrate_to_rds.py --dry-run

# 真实迁移（目标必须已配置 RDS）
python scripts/migrate_to_rds.py --apply

# 目标表已有数据时先清空，谨慎
python scripts/migrate_to_rds.py --apply --truncate
```

迁移脚本会按外键依赖顺序复制、分批写入，并逐表校验行数。

## 6. 重启与验证

```bash
python run.py --port 8080
```

验证标准：

1. 「系统接入」页 RDS、DCS Redis 状态为 **正常**，显示延迟与版本。
2. `/api/meta` 中 `cache_backend` 为 `redis`。
3. 登录、学习计划、错题、周报、强制学习、AI 探针与评审团均正常读写。
4. 重启服务后数据仍在（证明写入 RDS，而不是内存/SQLite）。

## 7. 网络与费用提醒

- **本机直连**：RDS/DCS 默认只提供内网地址。若应用运行在本机，需要：
  - 在控制台为 RDS 绑定公网 EIP / 开启公网访问；DCS 也需公网访问；或
  - 把应用部署到同 VPC 的 ECS 上（推荐，安全且延迟低）。
- **安全组**：务必只放行必要来源 IP，不要对 `0.0.0.0/0` 开放 3306/6379。
- **费用**：RDS 单机 40GB 与 DCS 1GB 均为计费资源，按实际使用计费；演示结束后及时释放或降配。
- **密码**：脚本会生成 16 位强密码并写入 `.env.cloud`；请勿提交到仓库或截图外发。

## 8. 当前阻塞

本机没有 AK/SK、项目 ID、VPC/子网/安全组与 DCS 规格编码，因此真实实例尚未创建，接入中心如实显示数据库/缓存未接入。完成本文档第 2–3 节后，即可执行第 4–6 节完成真实开通与验证。