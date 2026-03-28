# 问题 RSS 源测试清单

## 来源: issues/2026-03-24-rss-no-content.md (RSS 无正文)

### 分类 1: RSS Feed 只提供标题和链接
| 源名称 | Feed URL | 预期问题 |
|--------|----------|----------|
| Paul Graham Essays | http://www.aaronsw.com/2002/feeds/pgessays.rss | 代理 RSS，无正文 |
| Fabien Sanglard | https://fabiensanglard.net/rss.xml | RSS 无正文 |
| Mitchell Hashimoto | https://mitchellh.com/feed.xml | RSS 无正文 |
| Chad Nauseam | https://chadnauseam.com/rss.xml | RSS 无正文 |
| Google Cloud Security | https://cloudblog.withgoogle.com/products/identity-security/rss/ | RSS 无正文 |
| Eric Migicovsky | https://ericmigi.com/rss.xml | RSS 无正文 |
| hey.paris | https://hey.paris/index.xml | RSS 无正文 |
| Beej's Guide | https://beej.us/blog/rss.xml | RSS 无正文 |
| Jyn.dev | https://jyn.dev/atom.xml | RSS 无正文 |
| Group-IB Blog | https://www.group-ib.com/feed/blogfeed/ | RSS 无正文 |

### 分类 2: 内容极短
| 源名称 | Feed URL | 预期问题 |
|--------|----------|----------|
| Daniel Wirtz | https://danielwirtz.com/feed/ | 极短正文 |
| Simon Tatham | https://.chiark.greenend.org.uk/~sgtatham/atom.xml | 较短正文 |
| Auth0 Blog | https://auth0.com/blog/feed.xml | 较短正文 |

## 来源: issues/2026-03-24-rss-source-accessibility.md (RSS 可访问性问题)

### 分类 3: RSS 地址已废弃/迁移
| 源名称 | Feed URL | 预期问题 |
|--------|----------|----------|
| Anthropic Research | https://www.anthropic.com/research/rss.xml | 404 (需正确URL) |
| OpenAI Blog | https://openai.com/blog/rss.xml | 域名迁移 |
| Microsoft Security | https://www.microsoft.com/en-us/security/blog/feed/ | 地址更新 |
| Sysdig Blog | https://www.sysdig.com/feed/ | 域名重定向 |
| CSO Online | https://www.csoonline.com/feed/ | 地址更新 |

### 分类 4: 反爬限制
| 源名称 | Feed URL | 预期问题 |
|--------|----------|----------|
| Dark Reading | https://www.darkreading.com/rss.xml | 反爬限制 |
| Karpathy Blog | https://karpathy.bearblog.dev/feed/ | Bear Blog 反爬 |

### 分类 5: 连接问题
| 源名称 | Feed URL | 预期问题 |
|--------|----------|----------|
| Ted Unangst | https://www.tedunangst.com/flak/rss | 连接失败 |
| Rachel by the Bay | https://rachelbythebay.com/w/atom.xml | 连接失败 |