# 历史词典引文证据

主子方向为其他。词典编辑需要把历史文献中的原文、引文版本、拼写变体和义项判断组织成可复核的数据。可用自编的地域语料及自造词条启动，每条输入保留读法来源和编辑判断记录。

这是可运行的最小数据基线，只实现下表列明的能力。词条和引文来源是模拟记录。支持显式证据，不从正文推断转载关系或词义。

| 数据链 | 基线能力 | 离线样例 | 可核验结果 |
|---|---|---|---|
| `citation-lineage` | 沿明确的转载关系保留每条引文的路径，只统计可追到的独立原始用例。 | [输入](examples/citation-lineage.json) | [结果](tests/expected/citation-lineage.json) |
| `dated-word-forms` | 按有效年代、地域和词形应用已核对的映射，并保留多义候选。 | [输入](examples/dated-word-forms.json) | [结果](tests/expected/dated-word-forms.json) |
| `earliest-sense-dates` | 以署写证据优先、首刊次之形成可用日期区间，印本日期单列。 | [输入](examples/earliest-sense-dates.json) | [结果](tests/expected/earliest-sense-dates.json) |
| `sense-review` | 分开当前版标注和须重审的旧版引文，并报告当前义项冲突。 | [输入](examples/sense-review.json) | [结果](tests/expected/sense-review.json) |
| `corpus-coverage` | 按同类来源比较标准化历时用例率，并标记样本量不足的分组。 | [输入](examples/corpus-coverage.json) | [结果](tests/expected/corpus-coverage.json) |

## 运行

在仓库根目录使用 Python 3.11 及以上版本，无需安装运行依赖：

```sh
python3 -m historical_lexicon_evidence citation-lineage examples/citation-lineage.json
python3 -m historical_lexicon_evidence citation-lineage examples/citation-lineage.json --sqlite facts.sqlite
python3 -m unittest discover -s tests -v
```

每个输入文件包含 `records` 数组，记录的 `id` 在批内唯一。各数据链校验自己的业务字段，输出按 `fact_id` 标识的事实。起止范围若无另行说明均为左闭右开；日期、深度、金额和持续时间等单位由字段标明。

加上 `--sqlite` 时，`runs` 表保存规范化的来源 JSON 与 SHA-256，`facts` 表保存同一批次的事实。原样重放不新增事实；写入失败回滚整批。既有数据库不会被自动改写为不同版本的处理结果。JSON 接口和入库只是数据处理的运行入口，不是仓库的业务主体。
