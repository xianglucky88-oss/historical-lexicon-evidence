# 历史词典引文证据

主子方向为其他。词典编辑需要把历史文献中的原文、引文版本、拼写变体和义项判断组织成可复核的数据。可用自编的地域语料及自造词条启动，每条输入保留读法来源和编辑判断记录。

这是可运行的最小数据基线，只实现下表列明的能力。词条和引文来源是模拟记录。支持显式证据，不从正文推断转载关系或词义。

| 数据链 | 基线能力 | 离线样例 | 可核验结果 |
|---|---|---|---|
| `citation-lineage` | 沿明确的转载关系保留每条引文及其已审定片段的照录路径与起始版次，只统计可追到的独立原始用例。 | [输入](examples/citation-lineage.json) | [结果](tests/expected/citation-lineage.json) |
| `dated-word-forms` | 按有效年代、地域和词形应用已核对的映射，并保留多义候选。 | [输入](examples/dated-word-forms.json) | [结果](tests/expected/dated-word-forms.json) |
| `earliest-sense-dates` | 以署写证据优先、首刊次之形成可用日期区间，印本日期单列；义项拆分后按文字片段各自取证。 | [输入](examples/earliest-sense-dates.json) | [结果](tests/expected/earliest-sense-dates.json) |
| `sense-review` | 分开当前版标注和须重审的旧版引文，并报告当前义项冲突；可细分到文字片段。 | [输入](examples/sense-review.json) | [结果](tests/expected/sense-review.json) |
| `corpus-coverage` | 按同类来源比较标准化历时用例率，并标记样本量不足的分组。 | [输入](examples/corpus-coverage.json) | [结果](tests/expected/corpus-coverage.json) |

## 文字片段

义项拆分后，一条引文可能混有不同版次的文字：旧文字照录自初版，支持新义项的措辞却是修订本才添上的。要让来源和年代都能分开核对，可在 `citations` 的每一项上声明 `fragments` 数组，并给出该引文的 `edition`（版次标签）：

```json
{
  "citation": "S1",
  "edition": "选本 1850",
  "reprinted_from": "E2",
  "fragments": [
    {"fragment": "old", "relation": "verbatim", "copied_from": "E2/old",
     "dates": [{"kind": "edition", "year_min": 1850, "year_max": 1850}]},
    {"fragment": "added", "relation": "verbatim", "copied_from": "E2/added"}
  ]
}
```

- 片段引用写作 `引文/片段`（如 `E2/old`），跨引文、跨版次追查。
- `relation` 只取 `verbatim`（照录，必须给出 `copied_from`）、`new`（该版次首次出现）或 `unconfirmed`（未能确认，不得带 `copied_from`）。照录关系只按声明跟随，不按文本相似度猜测。
- 起始版次是链条上第一个关系为 `new` 的片段所在引文的 `edition`；`copied_from` 指向未声明片段、关系为 `unconfirmed` 或链条中断时，该片段保留为待核（`pending`），不推定来源。
- 选本重复摘录同一来源片段时，只以首次出现该文字的片段为一份独立用例（`origin`）；各选本的 `path` 仍逐条保留，可核对照录路径。一条引文的片段若追溯出不同起始版次，该引文的 `origin` 留空，由片段各自标明，便于看出旧文字与新增文字指向不同版次。
- 年代链（`earliest-sense-dates`）在片段模式下另需记录级 `definition_version` 和 `sense`；`dates` 与 `votes` 都挂在片段上。优先采用适用于该片段的 `written`，其次 `published`；`edition` 仅列出印期，不替代二者。`applies_to` 可把日期限定到具体片段（`引文/片段`）或起始片段；指向其他文字的日期会列入 `excluded_evidence` 且不采用。
- 以下片段不并入新义项最早年代，保留在 `pending`：审读结论仍为旧义项（`old_sense`）、只有旧版结论（`stale_review`）、当前结论互相冲突（`review_unresolved`）、承袭中断（`origin_unlocated`、`relation_unconfirmed`）或日期未能对应该文字（`date_mismatch`）。只有再版印期的列入 `undated`（`edition_only`）。同一片段的选本重复摘录只在首次出现的片段处成案，其余记为 `duplicate`。
- `earliest_range` 取各用例的下界与最小上界，`earliest_candidates` 保留所有下界不晚于该上界的用例，含下界恰好等于上界的用例。

## 运行

在仓库根目录使用 Python 3.11 及以上版本，无需安装运行依赖：

```sh
python3 -m historical_lexicon_evidence citation-lineage examples/citation-lineage.json
python3 -m historical_lexicon_evidence citation-lineage examples/citation-lineage.json --sqlite facts.sqlite
python3 -m unittest discover -s tests -v
```

每个输入文件包含 `records` 数组，记录的 `id` 在批内唯一。各数据链校验自己的业务字段，输出按 `fact_id` 标识的事实。起止范围若无另行说明均为左闭右开；日期、深度、金额和持续时间等单位由字段标明。

加上 `--sqlite` 时，`runs` 表保存规范化的来源 JSON 与 SHA-256，`facts` 表保存同一批次的事实。原样重放不新增事实；写入失败回滚整批。既有数据库不会被自动改写为不同版本的处理结果。JSON 接口和入库只是数据处理的运行入口，不是仓库的业务主体。
