# 回归测试映射（jiadian）

每个已关闭的问题都对应到具体的测试名，谁改了相关代码，测试会先叫。

| Issue | 问题 | 钉住它的测试 |
| --- | --- | --- |
| #3 | 残值算不出来时 CLI/Web 印 `残值约 None 元` | `test_integration.TestCliLayer::test_residual_none_is_explained` |
| #4 | 未知 POST 路径不读 body 就回 404，Windows 端 10053 | `test_integration.TestHttpLayer::test_unknown_post_path_drains_body` |
| #5 | `--file` 指向不存在文件时抛 traceback | `test_integration.TestCliLayer::test_missing_file_exit_2` |

## 为什么这样对应

- **#3** 断言的是输出文本（`残值约 算不出(缺购机年份) 元`）并且额外断言 `assertNotIn("None", ...)`。只断言前半句不够：只要有人把 `r["residual"]` 又拼回字符串，`None` 会立刻回来。
- **#4** 用裸 socket 分两段发 40KB body，而不是 `urllib` 打一发。理由：`urllib` 往往是「先发完再读」，中小 body 在 RST 之前就跑完了，测不出来。分两段并在中间停 50ms，才能稳定复现「服务端没读完就关连接」。这条测试改前稳定失败（10053），改后稳定通过。
- **#5** 断言的不仅是退出码 2，还有 `读不到文件` 这句话和 `assertNotIn("Traceback")`。只断言退出码会让「换个地方抛栈」也算过。

## 其它被测试钉住的口径

| 口径 | 测试 |
| --- | --- |
| 整机 1 年过期、压缩机 10 年仍在保（`expired` 不等于「全过保」） | `TestHttpLayer::test_diagnose_numbers` |
| 保修年限按 `--buy-year` 覆盖描述里的年份 | `TestHttpLayer::test_diagnose_buy_year_override` |
| 模型输出里的金额被换成「该费用」 | `TestModelLayer::test_money_is_stripped` |
| `--mock` 优先于已配置的 key | `TestModelLayer::test_force_mock_wins_over_key` |
| 四份真实描述各自的结论分支 | `TestCliLayer::test_diagnose_file_end_to_end`、`examples/out/*.md` |
