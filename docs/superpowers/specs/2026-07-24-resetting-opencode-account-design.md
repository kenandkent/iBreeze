# OpenCode 多渠道完整重置与重装设计

## 目标

提供一个项目内 Skill 和一个独立 Shell 脚本，在 macOS 或 Linux 上识别
OpenCode CLI 的实际安装渠道，卸载当前版本，按需清理缓存或完整删除账号数据，
再通过原渠道安装最新版。

主要使用场景是旧账号免费模型额度耗尽后，清除旧认证并切换新账号。

## 范围

脚本支持以下官方安装渠道：

- npm 全局包 `opencode-ai`
- pnpm 全局包 `opencode-ai`
- Bun 全局包 `opencode-ai`
- Yarn 全局包 `opencode-ai`
- Homebrew `anomalyco/tap/opencode`
- Homebrew core `opencode`
- 官方安装脚本生成的独立二进制

脚本不处理 OpenCode Desktop、IDE 扩展、Docker 临时容器、Arch 包、
Windows 包管理器、Mise 或 Nix。检测到这些渠道或无法确认归属时停止，并输出
人工处理提示，不自动切换到其他渠道。

## 命令接口

```bash
# 仅预览完整账号重置
bash scripts/reinstall-opencode-clean.sh --full-reset --dry-run

# 执行完整账号重置并重装
bash scripts/reinstall-opencode-clean.sh --full-reset --yes

# 保留配置、认证和会话，仅清缓存、状态并重装
bash scripts/reinstall-opencode-clean.sh --yes
```

`--full-reset` 删除认证、历史会话、数据库、全局配置、插件、缓存和状态。
任何实际变更都必须提供 `--yes`；`--dry-run` 不终止进程、不卸载、不删除文件、
不安装软件。

## 渠道检测

检测分为三层：

1. 记录 `command -v opencode`、解析后的真实路径和当前版本。
2. 查询可用包管理器是否拥有 `opencode-ai` 或 `opencode`。
3. 将包管理器根目录、Homebrew 前缀或官方安装目录与真实路径匹配。

只有一个候选渠道与当前 PATH 命中的二进制匹配时才继续。检测到多个匹配、
多个 OpenCode 副本或零匹配时返回非零状态，并打印所有候选，不猜测渠道。

## 卸载、清理与重装

执行顺序固定：

1. 输出版本、路径、渠道、清理模式和所有目标目录。
2. 精确查找当前用户的 `opencode` 进程；执行模式下发送 `TERM`，最多等待
   5 秒，不使用 `KILL`。
3. 调用 `opencode uninstall --force`。非完整重置模式增加
   `--keep-config --keep-data`。
4. 验证旧命令或原渠道包已不可用。
5. 清理官方 XDG 目录中残留的 `opencode` 子目录：
   - `${XDG_CACHE_HOME:-$HOME/.cache}/opencode`
   - `${XDG_CONFIG_HOME:-$HOME/.config}/opencode`
   - `${XDG_DATA_HOME:-$HOME/.local/share}/opencode`
   - `${XDG_STATE_HOME:-$HOME/.local/state}/opencode`
6. 使用记录的原渠道安装最新版。
7. 验证命令路径、版本、帮助命令和包管理器归属。
8. 完整重置模式额外运行 `opencode auth list`，要求结果为零凭据。

官方独立安装渠道复用原安装目录，并通过 HTTPS 下载官方安装脚本。其他渠道
分别使用其原包管理器，不做跨渠道降级。

## 删除安全边界

删除前将每个路径规范化，并同时满足：

- 路径非空且 basename 为 `opencode`
- 路径不是 `/`、`$HOME` 或 XDG 根目录
- 路径属于本次启动时计算并打印的白名单

脚本不扫描项目内 `.opencode` 目录，不清理 npm、pnpm、Bun、Yarn 或 Homebrew
共享缓存，也不修改 Shell 启动文件。自定义 `OPENCODE_CONFIG` 或
`OPENCODE_CONFIG_DIR` 仅提示，不自动删除，避免误删共享配置。

## 错误处理

- 缺少必要命令、渠道不明确或进程无法正常退出：卸载前停止。
- 官方卸载失败：停止，不清理数据、不重装。
- 任一残留目录删除失败：停止，不重装。
- 重装失败：保留“已卸载、未重装”状态，输出失败命令和渠道。
- 验证失败：返回非零状态并列出路径、版本、包归属或凭据检查差异。

脚本使用 `set -euo pipefail`，所有破坏性目标使用双引号和显式白名单。

## Skill 结构

`skills/resetting-opencode-account/SKILL.md` 负责：

- 判断用户需要缓存清理还是完整账号重置
- 在删除前明确不可恢复的数据范围
- 指导代理先运行 dry-run
- 调用项目根目录下的独立脚本
- 汇报渠道、清理范围、重装版本和认证状态

Skill 不复制脚本实现，避免两份卸载逻辑漂移。

## 测试与验收

自动测试在临时 HOME 和伪造包管理器环境中运行，不接触真实用户目录：

- 未提供 `--yes` 时拒绝执行
- `--dry-run` 不修改文件或调用包管理器
- 完整重置删除四类 OpenCode 数据并得到零凭据
- 缓存模式保留 config/data
- 每个支持渠道均按原渠道重装
- 多渠道、未知渠道和残留进程失败路径
- 恶意或异常 XDG 路径被白名单校验拒绝

真实环境验收要求：

- `opencode --version` 和 `opencode --help` 成功
- 当前命令归属与原安装渠道一致
- `--full-reset` 后 `opencode auth list` 显示零凭据
- 新账号可以通过 OpenCode 的连接流程重新登录
