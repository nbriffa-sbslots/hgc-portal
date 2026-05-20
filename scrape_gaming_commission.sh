#!/bin/bash

OUTPUT_FILE="gaming_platforms.csv"

BASE_URL="https://certifications.gamingcommission.gov.gr/publicRecordsOnline/_layouts/15/inplview.aspx"
MAIN_PAGE="https://certifications.gamingcommission.gov.gr/publicRecordsOnline/Lists/TMKY/AllItems.aspx"
LIST="%7B078D8F28-5222-4DC3-BAF7-78AD0C26106A%7D"
VIEW="%7B3EDE77FE-14CF-446B-984A-9CA3378B3B5B%7D"

FILTER_FIELD="Eidos"
FILTER_VALUE="%CE%A0%CE%B1%CE%B9%CE%B3%CE%BD%CE%AF%CE%BF%CF%85"

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

echo "Fetching main page to get Request Digest..."

MAIN_HTML=$(curl -s --http1.1 --compressed \
  -H "User-Agent: $UA" \
  -H "Accept: text/html" \
  -H "Sec-Fetch-Dest: document" \
  -H "Sec-Fetch-Mode: navigate" \
  -H "Sec-Fetch-Site: none" \
  -H "Sec-Fetch-User: ?1" \
  "$MAIN_PAGE")

DIGEST=$(echo "$MAIN_HTML" | grep -o 'id="__REQUESTDIGEST" value="[^"]*"' | sed 's/.*value="//;s/"//')

if [ -z "$DIGEST" ]; then
    echo "Failed to get Request Digest. Exiting."
    exit 1
fi

echo "Got Request Digest."

printf '\xEF\xBB\xBF' > "$OUTPUT_FILE"
echo "EniaiosKodikosAdeias,EmporikiOnomasia,Title,Kataskevastis,Xrisi,Katigoria,Eidos,Ekdosi,Created,Modified" >> "$OUTPUT_FILE"

NEXT_URL="${BASE_URL}?List=${LIST}&View=${VIEW}&ViewCount=34&IsXslView=TRUE&IsCSR=TRUE&SortField=Eidos&SortDir=Asc&FilterField1=${FILTER_FIELD}&FilterValue1=${FILTER_VALUE}"

PAGE_NUM=1

echo "Starting scrape (filtered by Eidos=Παιγνίου)..."

while [ -n "$NEXT_URL" ]; do
    echo "Fetching page $PAGE_NUM..."

    RESPONSE=$(curl -s --http1.1 --compressed -X POST \
        -H "User-Agent: $UA" \
        -H "Accept: application/json, text/javascript, */*; q=0.01" \
        -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
        -H "Referer: $MAIN_PAGE" \
        -H "X-Requested-With: XMLHttpRequest" \
        -H "X-RequestDigest: $DIGEST" \
        -H "Sec-Fetch-Dest: empty" \
        -H "Sec-Fetch-Mode: cors" \
        -H "Sec-Fetch-Site: same-origin" \
        "$NEXT_URL")

    ROW_COUNT=$(echo "$RESPONSE" | jq -r '.Row | length' 2>/dev/null)

    if [ -z "$ROW_COUNT" ] || [ "$ROW_COUNT" = "null" ] || [ "$ROW_COUNT" -eq 0 ] 2>/dev/null; then
        echo "No more rows found. Stopping."
        break
    fi

    echo "  Found $ROW_COUNT records"

    echo "$RESPONSE" | jq -r '
      def format_date:
        if . == null or . == "" then ""
        else
          split(" ") as $parts |
          ($parts[0] | split("/")) as $date |
          ($parts[1] | split(":")) as $time |
          ($parts[2] // "") as $ampm |
          ($date[0] | if (. | length) == 1 then "0" + . else . end) as $day |
          ($date[1] | if (. | length) == 1 then "0" + . else . end) as $month |
          $date[2] as $year |
          ($time[0] | tonumber) as $hour |
          $time[1] as $minute |
          (if $ampm == "μμ" and $hour != 12 then $hour + 12
           elif $ampm == "πμ" and $hour == 12 then 0
           else $hour end) as $hour24 |
          ($hour24 | tostring | if (. | length) == 1 then "0" + . else . end) as $hourStr |
          "\($day)/\($month)/\($year) \($hourStr):\($minute)"
        end;
      .Row[] | [
        .EniaiosKodikosAdeias,
        .EmporikiOnomasia,
        .Title,
        .Kataskevastis,
        .Xrisi,
        .Katigoria,
        .Eidos,
        .Ekdosi,
        (.Created | format_date),
        (.Modified | format_date)
      ] | @csv' >> "$OUTPUT_FILE"

    NEXT_HREF=$(echo "$RESPONSE" | jq -r '.NextHref // empty')

    if [ -z "$NEXT_HREF" ]; then
        echo "No more pages. Stopping."
        NEXT_URL=""
    else
        PARAMS="${NEXT_HREF#\?}"
        NEXT_URL="${BASE_URL}?List=${LIST}&${PARAMS}&IsXslView=TRUE&IsCSR=TRUE"
        PAGE_NUM=$((PAGE_NUM + 1))
        sleep 0.33
    fi
done

TOTAL_RECORDS=$(wc -l < "$OUTPUT_FILE")
TOTAL_RECORDS=$((TOTAL_RECORDS - 1))

echo ""
echo "Done! Scraped $TOTAL_RECORDS records to $OUTPUT_FILE"
