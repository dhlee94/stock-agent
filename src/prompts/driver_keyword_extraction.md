Analyze these news headlines for ${name} (${ticker}) and extract the TOP 5 most SPECIFIC keywords that drive this stock's price.

News Headlines:
${news_context}

High Volatility Dates (days with big price moves):
${volatility_dates}

## CRITICAL RULES:
1. **EXCLUDE generic financial terms** like: 뉴스, 전망, 상승, 하락, 시장, 동향, 분석, 주가, 투자, stock, market, news, update
2. **ONLY extract specific proper nouns or event names**:
   - Product names: HBM, DDR5, OLED, iPhone, GPU
   - Technologies: AI, 반도체, 2차전지, EV
   - Company events: 파업, 실적발표, 인수합병, 공급계약
   - Competitors/Partners: TSMC, 퀄컴, 엔비디아, 애플
   - Technical terms: 수율, 공정, 파운드리, 3nm

## Example BAD keywords (too generic):
["뉴스", "전망", "상승", "시장", "동향"]

## Example GOOD keywords (specific):
["HBM", "파업", "수율", "TSMC", "AI반도체"]

Output ONLY a JSON array of 5 SPECIFIC keywords:
