
# Epic 限免采集

GitHub Actions 每 6 小时运行，也可手动运行 `Update Games (ETL Smart Engine)`。

- Epic 官方促销接口读取国区、美区的当前活动及预告，遍历所有优惠，避免普通折扣遮住后续免费活动。
- FreeGameFindings RSS、EpicGamesPC RSS 和其乐福利区 RSS 补充发现官方促销列表之外的商品。其乐摘要不包含链接时读取原帖正文。
- 社区只提供候选链接。额外商品必须通过 Epic 官方商品页的结构化数据核验：对应商品为基础游戏、价格为零、有尚未到期的活动截止时间。长期免费、DLC、试玩以及站外任务不会因社区帖子直接发布。
- 图片预告由官方促销接口确认，不根据图片或帖子标题猜测领取时间。
- `epic_candidates.json` 保存候选来源和核验状态，候选移出短订阅列表后仍可继续核验。每轮最多核验 30 个，按上次核验时间轮转；45 天未在订阅中出现的候选移出队列。
- 官方核验已恢复收费或活动过期的商品，不会被当轮旧数据兜底重新加入。网络失败保留原有兜底行为。

本地检查：`python -m unittest discover -s tests -v`。

线上数据通过 Actions 中的 `API_BASE` Secret 指定的接口读写；仓库根目录的 `games.json` 并不是当前线上数据的可靠快照。运行完整工作流会写入线上数据，本地验证采集模块无需调用上传接口。

## 管理页直接发布

`admin/freegamestaffonly_ordered_fixed.html` 的“保存并发布”同步 `manager.yml` 后，直接调用现有线上接口更新有变化的数据文件，不触发 GitHub Actions 或抓取任务。请连接 `main` 分支，使手动发布与定时采集使用同一份配置。

先读取最新线上数据，再按人工规则合并，保留其他字段、特惠截图和额外情报分类。发布前检查 GitHub 文件 SHA 及线上数据变化；数据不完整、配置冲突时停止发布。多文件接口不支持事务，因此部分成功时会显示未完成，并保留重试状态。重试重新合并最新数据；GitHub 内容一致时不重复提交。

将两份 `admin/` 文件部署在同一目录，或生成可直接替换原管理页的单文件版本：

```sh
python scripts/build_admin.py /tmp/freegamestaffonly_ordered_fixed.html
```

新版不包含默认 GitHub Token，使用管理页连接配置中输入并保存在浏览器的信息。线上写入沿用现有 `POST /v1/update/steam-daily-free` 接口；浏览器需要后端允许管理页来源、POST 及 `Content-Type`、`filename` 请求头。当前执行环境无法连接该接口，真实跨域写入须在部署环境核验。配置先写 GitHub，线上失败不会回滚 GitHub；页面可重试发布。

发布规则测试：`node tests/test_admin_publish.cjs`。这些测试使用模拟接口，不修改生产数据。
