# 英语学习网站（自用）

剑桥雅思阅读题库 + 点词查询（单词和短语都能离线查）+ 生词本 + 《English Phrasal Verbs in Use》短语学习。
只在自己的电脑和手机上用，**不要放到公网**（书有版权）。

## 第一次运行前：准备词典

**运行前需要下载 ECDICT 并生成 `data/dict.db`**（130MB，太大不放进仓库）。换电脑或者 clone 下来后，在项目文件夹里执行一次：

```bash
mkdir -p data/raw/ecdict
curl -L -o data/raw/ecdict/ecdict.csv https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv
python3 scripts/build_dict.py
```

下载约 65MB，生成大约 10 秒。ECDICT 是开源英汉词典（MIT 协议），项目地址 https://github.com/skywind3000/ECDICT 。

## 怎么打开

- **电脑**：双击 `启动英语学习.command`，浏览器会自动打开 http://localhost:8848
  （第一次双击 macOS 可能提示"无法验证开发者"：右键这个文件 → 打开 → 打开。）
- **手机**：手机和 Mac 连同一个 WiFi（或 Mac 连着手机热点），在手机浏览器打开启动窗口里显示的
  `http://192.168.x.x:8848` 这种地址。Safari 里点"分享 → 添加到主屏幕"，以后就像 App 一样打开。
  第一次有手机访问时，macOS 可能会弹窗问"是否允许 python3 接受传入连接"，选允许。
- 关掉启动的那个终端窗口，网站就停了。

## 功能

| 页面 | 能做什么 |
|---|---|
| 题库 | 剑18、剑19（A 类）和剑11、剑13（G 类）共 16 套、48 篇阅读。左边文章，右边题目（全部是文字版，直接在题目里填空、点选），提交后自动判分，计时，做题记录 |
| 工具栏 | 🖱 **鼠标**（默认）：不用笔，正常选择、复制文字。🖊 **学习笔**：点词翻译、拖选查短语（只有选中学习笔才翻译）。🖍 **记号笔**：点一个词或拖选一段来标记，再点一次记号笔可以换颜色、选"荧光笔/下划线"。🧽 **橡皮擦**：点标记擦掉，或拖选一段擦掉。标记自动保存 |
| 计时 | 默认关闭。点「计时」选倒计时（20 / 40 / 60 分钟或自己输入）或正计时；计时中再点可以暂停、继续、重新设置、关闭。时间到会提示，超出的时间显示为 + |
| 点词查询 | 学习笔模式下：点一个词显示音标、中文、发音，并自动认出它所在的短语（例如点 gave 认出 give up）。拖选几个词：查短语。手机上长按选中后点"查询所选" |
| 生词本 | 查词时一键加入，自动记下出处句子；可以删除（有撤销）、写笔记、手动添加。文章里会用浅绿底色标出生词 |
| 复习 | 按记忆曲线安排复习（忘了 / 模糊 / 认识 / 太简单），键盘可用空格和 1–4 |
| 短语 | 70 个单元，每个单元的短语清单（中文 + 英文释义，来自书后 Mini dictionary）。「讲解和练习」和题库一样是文字版：左边讲解（可以点词、标记），右边练习直接填空、选择，点「对答案」自动判分并显示答案。页面底部可以展开看原书页面 |
| 写作 | 每套题的 Task 1/2 原题 + 写作框（自动保存、字数统计）+ 书后范文 |

## 数据在哪

- `data/user.db`：**你的生词本、做题记录、写作草稿都在这里，备份这一个文件就行。**
- `data/dict.db`：离线词典（开源 ECDICT，77 万词条，其中 36 万短语）
- `content/`：从书里提取出来的题库和页面图片
- `content-src/answers.txt`：阅读答案，是对照原书答案页手工核对录入的（640 题）
- `content-src/questions/*.md`：阅读题目，是对照原书题目页手工转写的（48 篇）。格式说明在 `web/questions.js` 开头，发现错字可以直接改，改完运行 `python3 scripts/build_content.py`

## 短语书文字版怎么来的

`python3 scripts/build_pv.py` 会按 OCR 的版面（`data/ocr/phrasal-verbs.json`）自动还原每个单元：小节、表格、对话、练习题、填空（`scripts/pv_layout.py`）。
自动还原难免有错字或排版不对，以原书页面为准。并排的几栏（几封信、两栏日记、正文旁边的注释）会先读完一栏再读下一栏。
练习数和答案对不上的单元会退回显示原书图片（目前 70 个单元都是文字版）。

OCR 漏掉了题号或者填空的点（版面上推不出来）时，在 `content-src/pv/ocr-fixes.json` 里按页码和位置补上，只写位置和要补的题号，不用抄原文。

想手工修某个单元：

```bash
python3 scripts/pv_layout.py 12 > content-src/pv/12.md   # 导出自动还原的结果
# 编辑 content-src/pv/12.md（格式说明在 web/pv.js 开头）
python3 scripts/build_pv.py                              # 有 content-src/pv/NN.md 的单元优先用手工版
```

## 文字识别说明

剑19 是扫描版，其他几本的文字层也有错字，所以全部用 macOS 自带的 Vision 重新识别过。
文章正文、段落字母都检查过，但难免有个别字识别错。每篇文章底部有"看原书页面"，以原书为准。

## 加新书（以后补剑14–17、剑20 时）

1. PDF 放进 `books/`，起个短名字，例如 `c20a.pdf`
2. 识别文字：`./bin/ocr books/c20a.pdf data/ocr/c20a.json`（约 10 分钟）
3. 渲染页面图：`python3 scripts/render_pages.py c20a`
4. 在 `scripts/build_content.py` 的 `BOOKS` 里加一行
5. 对照书后答案页，把阅读答案按格式加进 `content-src/answers.txt`
6. 对照题目页，把题目转写成 `content-src/questions/<篇章id>.md`（没有转写的篇章会自动显示原书图片 + 答题卡）
7. `python3 scripts/parse_answers.py && python3 scripts/build_content.py && python3 scripts/check_questions.py`

这一步可以直接让 Claude 帮你做。

## 脚本一览

| 脚本 | 作用 |
|---|---|
| `server.py` | 网站服务器（只用 Python 自带的库） |
| `scripts/ocr.swift` | 调用 macOS Vision 识别 PDF 文字（编译好的在 `bin/ocr`） |
| `scripts/build_dict.py` | 把 ECDICT 转成 `data/dict.db` |
| `scripts/render_pages.py` | 把 PDF 每页渲染成图片 |
| `scripts/build_content.py` | 从识别结果里切出文章、题目页、写作题 |
| `scripts/parse_answers.py` | 把 `answers.txt` 转成判分用的数据 |
| `scripts/build_pv.py` | 短语书：单元、短语清单、答案页 |
| `scripts/check_questions.py` | 检查转写的题目：每道题都出现且只出现一次 |
| `web/questions.js` | 把题目文字渲染成可作答的题目（格式说明在文件开头） |
| `web/marks.js` | 学习笔 / 记号笔 / 橡皮擦 |
