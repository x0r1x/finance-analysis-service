# Formula graph

- Schema: `1.7.0`
- Job: `2eca70a9acd0c7b1812adcb2e1a4aacc84092f52726d001a93b9564950e5dd5e`
- Nodes: 4806
- Edges: 11370
- Iterate: false
- Links: 2973
- Unresolved: 0
- Dangling: 0

## Kinds

- range: 6990
- ref: 1817
- cross_sheet: 2563

## Empty cells

- empty_range_member: 714
- empty_ref: 4

## Circularity

- Construction row 19: Uses of funds for circularity breakdown purpose

## Links

| Cell | Row | Period | Class | Formula | Refs |
| --- | --- | --- | --- | --- | --- |
| Amortization!AA10 | Amortization\|10\|Amortization!r2 | Y23 | same_period | AA8+AA13 | Amortization!AA8, Amortization!AA13 |
| Amortization!AA13 | Amortization\|13\|Amortization!r2 | Y23 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!Z10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!Z10 |
| Amortization!AA8 | Amortization\|8\|Amortization!r2 | Y23 | rollforward | Z10+Construction!AA19 | Amortization!Z10, Construction!AA19 |
| Amortization!AB10 | Amortization\|10\|Amortization!r2 | Y24 | same_period | AB8+AB13 | Amortization!AB8, Amortization!AB13 |
| Amortization!AB13 | Amortization\|13\|Amortization!r2 | Y24 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AA10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AA10 |
| Amortization!AB8 | Amortization\|8\|Amortization!r2 | Y24 | rollforward | AA10+Construction!AB19 | Amortization!AA10, Construction!AB19 |
| Amortization!AC10 | Amortization\|10\|Amortization!r2 | Y25 | same_period | AC8+AC13 | Amortization!AC8, Amortization!AC13 |
| Amortization!AC13 | Amortization\|13\|Amortization!r2 | Y25 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AB10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AB10 |
| Amortization!AC8 | Amortization\|8\|Amortization!r2 | Y25 | rollforward | AB10+Construction!AC19 | Amortization!AB10, Construction!AC19 |
| Amortization!AD10 | Amortization\|10\|Amortization!r2 | Y26 | same_period | AD8+AD13 | Amortization!AD8, Amortization!AD13 |
| Amortization!AD13 | Amortization\|13\|Amortization!r2 | Y26 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AC10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AC10 |
| Amortization!AD8 | Amortization\|8\|Amortization!r2 | Y26 | rollforward | AC10+Construction!AD19 | Amortization!AC10, Construction!AD19 |
| Amortization!AE10 | Amortization\|10\|Amortization!r2 | Y27 | same_period | AE8+AE13 | Amortization!AE8, Amortization!AE13 |
| Amortization!AE13 | Amortization\|13\|Amortization!r2 | Y27 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AD10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AD10 |
| Amortization!AE8 | Amortization\|8\|Amortization!r2 | Y27 | rollforward | AD10+Construction!AE19 | Amortization!AD10, Construction!AE19 |
| Amortization!AF10 | Amortization\|10\|Amortization!r2 | Y28 | same_period | AF8+AF13 | Amortization!AF8, Amortization!AF13 |
| Amortization!AF13 | Amortization\|13\|Amortization!r2 | Y28 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AE10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AE10 |
| Amortization!AF8 | Amortization\|8\|Amortization!r2 | Y28 | rollforward | AE10+Construction!AF19 | Amortization!AE10, Construction!AF19 |
| Amortization!AG10 | Amortization\|10\|Amortization!r2 | Y29 | same_period | AG8+AG13 | Amortization!AG8, Amortization!AG13 |
| Amortization!AG13 | Amortization\|13\|Amortization!r2 | Y29 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AF10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AF10 |
| Amortization!AG8 | Amortization\|8\|Amortization!r2 | Y29 | rollforward | AF10+Construction!AG19 | Amortization!AF10, Construction!AG19 |
| Amortization!AH10 | Amortization\|10\|Amortization!r2 | Y30 | same_period | AH8+AH13 | Amortization!AH8, Amortization!AH13 |
| Amortization!AH13 | Amortization\|13\|Amortization!r2 | Y30 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AG10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AG10 |
| Amortization!AH8 | Amortization\|8\|Amortization!r2 | Y30 | rollforward | AG10+Construction!AH19 | Amortization!AG10, Construction!AH19 |
| Amortization!AI10 | Amortization\|10\|Amortization!r2 | Y31 | same_period | AI8+AI13 | Amortization!AI8, Amortization!AI13 |
| Amortization!AI13 | Amortization\|13\|Amortization!r2 | Y31 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AH10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AH10 |
| Amortization!AI8 | Amortization\|8\|Amortization!r2 | Y31 | rollforward | AH10+Construction!AI19 | Amortization!AH10, Construction!AI19 |
| Amortization!AJ10 | Amortization\|10\|Amortization!r2 | Y32 | same_period | AJ8+AJ13 | Amortization!AJ8, Amortization!AJ13 |
| Amortization!AJ13 | Amortization\|13\|Amortization!r2 | Y32 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AI10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AI10 |
| Amortization!AJ8 | Amortization\|8\|Amortization!r2 | Y32 | rollforward | AI10+Construction!AJ19 | Amortization!AI10, Construction!AJ19 |
| Amortization!AK10 | Amortization\|10\|Amortization!r2 | Y33 | same_period | AK8+AK13 | Amortization!AK8, Amortization!AK13 |
| Amortization!AK13 | Amortization\|13\|Amortization!r2 | Y33 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AJ10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AJ10 |
| Amortization!AK8 | Amortization\|8\|Amortization!r2 | Y33 | rollforward | AJ10+Construction!AK19 | Amortization!AJ10, Construction!AK19 |
| Amortization!AL10 | Amortization\|10\|Amortization!r2 | Y34 | same_period | AL8+AL13 | Amortization!AL8, Amortization!AL13 |
| Amortization!AL13 | Amortization\|13\|Amortization!r2 | Y34 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AK10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AK10 |
| Amortization!AL8 | Amortization\|8\|Amortization!r2 | Y34 | rollforward | AK10+Construction!AL19 | Amortization!AK10, Construction!AL19 |
| Amortization!AM10 | Amortization\|10\|Amortization!r2 | Y35 | same_period | AM8+AM13 | Amortization!AM8, Amortization!AM13 |
| Amortization!AM13 | Amortization\|13\|Amortization!r2 | Y35 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AL10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AL10 |
| Amortization!AM8 | Amortization\|8\|Amortization!r2 | Y35 | rollforward | AL10+Construction!AM19 | Amortization!AL10, Construction!AM19 |
| Amortization!AN10 | Amortization\|10\|Amortization!r2 | Y36 | same_period | AN8+AN13 | Amortization!AN8, Amortization!AN13 |
| Amortization!AN13 | Amortization\|13\|Amortization!r2 | Y36 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AM10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AM10 |
| Amortization!AN8 | Amortization\|8\|Amortization!r2 | Y36 | rollforward | AM10+Construction!AN19 | Amortization!AM10, Construction!AN19 |
| Amortization!AO10 | Amortization\|10\|Amortization!r2 | Y37 | same_period | AO8+AO13 | Amortization!AO8, Amortization!AO13 |
| Amortization!AO13 | Amortization\|13\|Amortization!r2 | Y37 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AN10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AN10 |
| Amortization!AO8 | Amortization\|8\|Amortization!r2 | Y37 | rollforward | AN10+Construction!AO19 | Amortization!AN10, Construction!AO19 |
| Amortization!AP10 | Amortization\|10\|Amortization!r2 | Y38 | same_period | AP8+AP13 | Amortization!AP8, Amortization!AP13 |
| Amortization!AP13 | Amortization\|13\|Amortization!r2 | Y38 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AO10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AO10 |
| Amortization!AP8 | Amortization\|8\|Amortization!r2 | Y38 | rollforward | AO10+Construction!AP19 | Amortization!AO10, Construction!AP19 |
| Amortization!AQ10 | Amortization\|10\|Amortization!r2 | Y39 | same_period | AQ8+AQ13 | Amortization!AQ8, Amortization!AQ13 |
| Amortization!AQ13 | Amortization\|13\|Amortization!r2 | Y39 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AP10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AP10 |
| Amortization!AQ8 | Amortization\|8\|Amortization!r2 | Y39 | rollforward | AP10+Construction!AQ19 | Amortization!AP10, Construction!AQ19 |
| Amortization!AR10 | Amortization\|10\|Amortization!r2 | Y40 | same_period | AR8+AR13 | Amortization!AR8, Amortization!AR13 |
| Amortization!AR13 | Amortization\|13\|Amortization!r2 | Y40 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!AQ10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!AQ10 |
| Amortization!AR8 | Amortization\|8\|Amortization!r2 | Y40 | rollforward | AQ10+Construction!AR19 | Amortization!AQ10, Construction!AR19 |
| Amortization!D13 | Amortization\|13\|Amortization!r2 |  | aggregation | SUM(E13:AR13) | Amortization!E13:AR13 |
| Amortization!E10 | Amortization\|10\|Amortization!r2 | Y1 | same_period | E8+E13 | Amortization!E8, Amortization!E13 |
| Amortization!E13 | Amortization\|13\|Amortization!r2 | Y1 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!D10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!D10 |
| Amortization!E8 | Amortization\|8\|Amortization!r2 | Y1 | same_period | D10+Construction!E19 | Amortization!D10, Construction!E19 |
| Amortization!F10 | Amortization\|10\|Amortization!r2 | Y2 | same_period | F8+F13 | Amortization!F8, Amortization!F13 |
| Amortization!F13 | Amortization\|13\|Amortization!r2 | Y2 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!E10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!E10 |
| Amortization!F8 | Amortization\|8\|Amortization!r2 | Y2 | rollforward | E10+Construction!F19 | Amortization!E10, Construction!F19 |
| Amortization!G10 | Amortization\|10\|Amortization!r2 | Y3 | same_period | G8+G13 | Amortization!G8, Amortization!G13 |
| Amortization!G13 | Amortization\|13\|Amortization!r2 | Y3 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!F10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!F10 |
| Amortization!G8 | Amortization\|8\|Amortization!r2 | Y3 | rollforward | F10+Construction!G19 | Amortization!F10, Construction!G19 |
| Amortization!H10 | Amortization\|10\|Amortization!r2 | Y4 | same_period | H8+H13 | Amortization!H8, Amortization!H13 |
| Amortization!H13 | Amortization\|13\|Amortization!r2 | Y4 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!G10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!G10 |
| Amortization!H8 | Amortization\|8\|Amortization!r2 | Y4 | rollforward | G10+Construction!H19 | Amortization!G10, Construction!H19 |
| Amortization!I10 | Amortization\|10\|Amortization!r2 | Y5 | same_period | I8+I13 | Amortization!I8, Amortization!I13 |
| Amortization!I13 | Amortization\|13\|Amortization!r2 | Y5 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!H10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!H10 |
| Amortization!I8 | Amortization\|8\|Amortization!r2 | Y5 | rollforward | H10+Construction!I19 | Amortization!H10, Construction!I19 |
| Amortization!J10 | Amortization\|10\|Amortization!r2 | Y6 | same_period | J8+J13 | Amortization!J8, Amortization!J13 |
| Amortization!J13 | Amortization\|13\|Amortization!r2 | Y6 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!I10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!I10 |
| Amortization!J8 | Amortization\|8\|Amortization!r2 | Y6 | rollforward | I10+Construction!J19 | Amortization!I10, Construction!J19 |
| Amortization!K10 | Amortization\|10\|Amortization!r2 | Y7 | same_period | K8+K13 | Amortization!K8, Amortization!K13 |
| Amortization!K13 | Amortization\|13\|Amortization!r2 | Y7 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!J10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!J10 |
| Amortization!K8 | Amortization\|8\|Amortization!r2 | Y7 | rollforward | J10+Construction!K19 | Amortization!J10, Construction!K19 |
| Amortization!L10 | Amortization\|10\|Amortization!r2 | Y8 | same_period | L8+L13 | Amortization!L8, Amortization!L13 |
| Amortization!L13 | Amortization\|13\|Amortization!r2 | Y8 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!K10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!K10 |
| Amortization!L8 | Amortization\|8\|Amortization!r2 | Y8 | rollforward | K10+Construction!L19 | Amortization!K10, Construction!L19 |
| Amortization!M10 | Amortization\|10\|Amortization!r2 | Y9 | same_period | M8+M13 | Amortization!M8, Amortization!M13 |
| Amortization!M13 | Amortization\|13\|Amortization!r2 | Y9 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!L10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!L10 |
| Amortization!M8 | Amortization\|8\|Amortization!r2 | Y9 | rollforward | L10+Construction!M19 | Amortization!L10, Construction!M19 |
| Amortization!N10 | Amortization\|10\|Amortization!r2 | Y10 | same_period | N8+N13 | Amortization!N8, Amortization!N13 |
| Amortization!N13 | Amortization\|13\|Amortization!r2 | Y10 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!M10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!M10 |
| Amortization!N8 | Amortization\|8\|Amortization!r2 | Y10 | rollforward | M10+Construction!N19 | Amortization!M10, Construction!N19 |
| Amortization!O10 | Amortization\|10\|Amortization!r2 | Y11 | same_period | O8+O13 | Amortization!O8, Amortization!O13 |
| Amortization!O13 | Amortization\|13\|Amortization!r2 | Y11 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!N10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!N10 |
| Amortization!O8 | Amortization\|8\|Amortization!r2 | Y11 | rollforward | N10+Construction!O19 | Amortization!N10, Construction!O19 |
| Amortization!P10 | Amortization\|10\|Amortization!r2 | Y12 | same_period | P8+P13 | Amortization!P8, Amortization!P13 |
| Amortization!P13 | Amortization\|13\|Amortization!r2 | Y12 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!O10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!O10 |
| Amortization!P8 | Amortization\|8\|Amortization!r2 | Y12 | rollforward | O10+Construction!P19 | Amortization!O10, Construction!P19 |
| Amortization!Q10 | Amortization\|10\|Amortization!r2 | Y13 | same_period | Q8+Q13 | Amortization!Q8, Amortization!Q13 |
| Amortization!Q13 | Amortization\|13\|Amortization!r2 | Y13 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!P10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!P10 |
| Amortization!Q8 | Amortization\|8\|Amortization!r2 | Y13 | rollforward | P10+Construction!Q19 | Amortization!P10, Construction!Q19 |
| Amortization!R10 | Amortization\|10\|Amortization!r2 | Y14 | same_period | R8+R13 | Amortization!R8, Amortization!R13 |
| Amortization!R13 | Amortization\|13\|Amortization!r2 | Y14 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!Q10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!Q10 |
| Amortization!R8 | Amortization\|8\|Amortization!r2 | Y14 | rollforward | Q10+Construction!R19 | Amortization!Q10, Construction!R19 |
| Amortization!S10 | Amortization\|10\|Amortization!r2 | Y15 | same_period | S8+S13 | Amortization!S8, Amortization!S13 |
| Amortization!S13 | Amortization\|13\|Amortization!r2 | Y15 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!R10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!R10 |
| Amortization!S8 | Amortization\|8\|Amortization!r2 | Y15 | rollforward | R10+Construction!S19 | Amortization!R10, Construction!S19 |
| Amortization!T10 | Amortization\|10\|Amortization!r2 | Y16 | same_period | T8+T13 | Amortization!T8, Amortization!T13 |
| Amortization!T13 | Amortization\|13\|Amortization!r2 | Y16 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!S10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!S10 |
| Amortization!T8 | Amortization\|8\|Amortization!r2 | Y16 | rollforward | S10+Construction!T19 | Amortization!S10, Construction!T19 |
| Amortization!U10 | Amortization\|10\|Amortization!r2 | Y17 | same_period | U8+U13 | Amortization!U8, Amortization!U13 |
| Amortization!U13 | Amortization\|13\|Amortization!r2 | Y17 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!T10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!T10 |
| Amortization!U8 | Amortization\|8\|Amortization!r2 | Y17 | rollforward | T10+Construction!U19 | Amortization!T10, Construction!U19 |
| Amortization!V10 | Amortization\|10\|Amortization!r2 | Y18 | same_period | V8+V13 | Amortization!V8, Amortization!V13 |
| Amortization!V13 | Amortization\|13\|Amortization!r2 | Y18 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!U10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!U10 |
| Amortization!V8 | Amortization\|8\|Amortization!r2 | Y18 | rollforward | U10+Construction!V19 | Amortization!U10, Construction!V19 |
| Amortization!W10 | Amortization\|10\|Amortization!r2 | Y19 | same_period | W8+W13 | Amortization!W8, Amortization!W13 |
| Amortization!W13 | Amortization\|13\|Amortization!r2 | Y19 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!V10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!V10 |
| Amortization!W8 | Amortization\|8\|Amortization!r2 | Y19 | rollforward | V10+Construction!W19 | Amortization!V10, Construction!W19 |
| Amortization!X10 | Amortization\|10\|Amortization!r2 | Y20 | same_period | X8+X13 | Amortization!X8, Amortization!X13 |
| Amortization!X13 | Amortization\|13\|Amortization!r2 | Y20 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!W10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!W10 |
| Amortization!X8 | Amortization\|8\|Amortization!r2 | Y20 | rollforward | W10+Construction!X19 | Amortization!W10, Construction!X19 |
| Amortization!Y10 | Amortization\|10\|Amortization!r2 | Y21 | same_period | Y8+Y13 | Amortization!Y8, Amortization!Y13 |
| Amortization!Y13 | Amortization\|13\|Amortization!r2 | Y21 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!X10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!X10 |
| Amortization!Y8 | Amortization\|8\|Amortization!r2 | Y21 | rollforward | X10+Construction!Y19 | Amortization!X10, Construction!Y19 |
| Amortization!Z10 | Amortization\|10\|Amortization!r2 | Y22 | same_period | Z8+Z13 | Amortization!Z8, Amortization!Z13 |
| Amortization!Z13 | Amortization\|13\|Amortization!r2 | Y22 | same_period | -Construction!$C$20/('Input Assumptions'!$D$8-'Input Assumptions'!$D$9)*TBA!Y10 | Construction!C20, Input Assumptions!D8, Input Assumptions!D9, TBA!Y10 |
| Amortization!Z8 | Amortization\|8\|Amortization!r2 | Y22 | rollforward | Y10+Construction!Z19 | Amortization!Y10, Construction!Z19 |
| Balance Sheet!AA10 | Balance Sheet\|10\|Balance Sheet!r3 | Y22 | aggregation | SUM(AA8:AA9) | Balance Sheet!AA8:AA9 |
| Balance Sheet!AA13 | Balance Sheet\|13\|Balance Sheet!r3 | Y22 | aggregation | SUM(Construction!$E$26:Z26) | Construction!E26:Z26 |
| Balance Sheet!AA14 | Balance Sheet\|14\|Balance Sheet!r3 | Y22 | rollforward | 'P&L'!AA25+CFS!AA21+'Balance Sheet'!Z14 | P&L!AA25, CFS!AA21, Balance Sheet!Z14 |
| Balance Sheet!AA15 | Balance Sheet\|15\|Balance Sheet!r3 | Y22 | same_period | Debt!AA11 | Debt!AA11 |
| Balance Sheet!AA16 | Balance Sheet\|16\|Balance Sheet!r3 | Y22 | aggregation | SUM(AA13:AA15) | Balance Sheet!AA13:AA15 |
| Balance Sheet!AA19 | Balance Sheet\|19\|Balance Sheet!r3 | Y22 | same_period | AA10-AA16<0.01 | Balance Sheet!AA10, Balance Sheet!AA16 |
| Balance Sheet!AA8 | Balance Sheet\|8\|Balance Sheet!r3 | Y22 | same_period | Amortization!Z10 | Amortization!Z10 |
| Balance Sheet!AA9 | Balance Sheet\|9\|Balance Sheet!r3 | Y22 | same_period | CFS!AA25 | CFS!AA25 |
| Balance Sheet!AB10 | Balance Sheet\|10\|Balance Sheet!r3 | Y23 | aggregation | SUM(AB8:AB9) | Balance Sheet!AB8:AB9 |
| Balance Sheet!AB13 | Balance Sheet\|13\|Balance Sheet!r3 | Y23 | aggregation | SUM(Construction!$E$26:AA26) | Construction!E26:AA26 |
| Balance Sheet!AB14 | Balance Sheet\|14\|Balance Sheet!r3 | Y23 | rollforward | 'P&L'!AB25+CFS!AB21+'Balance Sheet'!AA14 | P&L!AB25, CFS!AB21, Balance Sheet!AA14 |
| Balance Sheet!AB15 | Balance Sheet\|15\|Balance Sheet!r3 | Y23 | same_period | Debt!AB11 | Debt!AB11 |
| Balance Sheet!AB16 | Balance Sheet\|16\|Balance Sheet!r3 | Y23 | aggregation | SUM(AB13:AB15) | Balance Sheet!AB13:AB15 |
| Balance Sheet!AB19 | Balance Sheet\|19\|Balance Sheet!r3 | Y23 | same_period | AB10-AB16<0.01 | Balance Sheet!AB10, Balance Sheet!AB16 |
| Balance Sheet!AB8 | Balance Sheet\|8\|Balance Sheet!r3 | Y23 | same_period | Amortization!AA10 | Amortization!AA10 |
| Balance Sheet!AB9 | Balance Sheet\|9\|Balance Sheet!r3 | Y23 | same_period | CFS!AB25 | CFS!AB25 |
| Balance Sheet!AC10 | Balance Sheet\|10\|Balance Sheet!r3 | Y24 | aggregation | SUM(AC8:AC9) | Balance Sheet!AC8:AC9 |
| Balance Sheet!AC13 | Balance Sheet\|13\|Balance Sheet!r3 | Y24 | aggregation | SUM(Construction!$E$26:AB26) | Construction!E26:AB26 |
| Balance Sheet!AC14 | Balance Sheet\|14\|Balance Sheet!r3 | Y24 | rollforward | 'P&L'!AC25+CFS!AC21+'Balance Sheet'!AB14 | P&L!AC25, CFS!AC21, Balance Sheet!AB14 |
| Balance Sheet!AC15 | Balance Sheet\|15\|Balance Sheet!r3 | Y24 | same_period | Debt!AC11 | Debt!AC11 |
| Balance Sheet!AC16 | Balance Sheet\|16\|Balance Sheet!r3 | Y24 | aggregation | SUM(AC13:AC15) | Balance Sheet!AC13:AC15 |
| Balance Sheet!AC19 | Balance Sheet\|19\|Balance Sheet!r3 | Y24 | same_period | AC10-AC16<0.01 | Balance Sheet!AC10, Balance Sheet!AC16 |
| Balance Sheet!AC8 | Balance Sheet\|8\|Balance Sheet!r3 | Y24 | same_period | Amortization!AB10 | Amortization!AB10 |
| Balance Sheet!AC9 | Balance Sheet\|9\|Balance Sheet!r3 | Y24 | same_period | CFS!AC25 | CFS!AC25 |
| Balance Sheet!AD10 | Balance Sheet\|10\|Balance Sheet!r3 | Y25 | aggregation | SUM(AD8:AD9) | Balance Sheet!AD8:AD9 |
| Balance Sheet!AD13 | Balance Sheet\|13\|Balance Sheet!r3 | Y25 | aggregation | SUM(Construction!$E$26:AC26) | Construction!E26:AC26 |
| Balance Sheet!AD14 | Balance Sheet\|14\|Balance Sheet!r3 | Y25 | rollforward | 'P&L'!AD25+CFS!AD21+'Balance Sheet'!AC14 | P&L!AD25, CFS!AD21, Balance Sheet!AC14 |
| Balance Sheet!AD15 | Balance Sheet\|15\|Balance Sheet!r3 | Y25 | same_period | Debt!AD11 | Debt!AD11 |
| Balance Sheet!AD16 | Balance Sheet\|16\|Balance Sheet!r3 | Y25 | aggregation | SUM(AD13:AD15) | Balance Sheet!AD13:AD15 |
| Balance Sheet!AD19 | Balance Sheet\|19\|Balance Sheet!r3 | Y25 | same_period | AD10-AD16<0.01 | Balance Sheet!AD10, Balance Sheet!AD16 |
| Balance Sheet!AD8 | Balance Sheet\|8\|Balance Sheet!r3 | Y25 | same_period | Amortization!AC10 | Amortization!AC10 |
| Balance Sheet!AD9 | Balance Sheet\|9\|Balance Sheet!r3 | Y25 | same_period | CFS!AD25 | CFS!AD25 |
| Balance Sheet!AE10 | Balance Sheet\|10\|Balance Sheet!r3 | Y26 | aggregation | SUM(AE8:AE9) | Balance Sheet!AE8:AE9 |
| Balance Sheet!AE13 | Balance Sheet\|13\|Balance Sheet!r3 | Y26 | aggregation | SUM(Construction!$E$26:AD26) | Construction!E26:AD26 |
| Balance Sheet!AE14 | Balance Sheet\|14\|Balance Sheet!r3 | Y26 | rollforward | 'P&L'!AE25+CFS!AE21+'Balance Sheet'!AD14 | P&L!AE25, CFS!AE21, Balance Sheet!AD14 |
| Balance Sheet!AE15 | Balance Sheet\|15\|Balance Sheet!r3 | Y26 | same_period | Debt!AE11 | Debt!AE11 |
| Balance Sheet!AE16 | Balance Sheet\|16\|Balance Sheet!r3 | Y26 | aggregation | SUM(AE13:AE15) | Balance Sheet!AE13:AE15 |
| Balance Sheet!AE19 | Balance Sheet\|19\|Balance Sheet!r3 | Y26 | same_period | AE10-AE16<0.01 | Balance Sheet!AE10, Balance Sheet!AE16 |
| Balance Sheet!AE8 | Balance Sheet\|8\|Balance Sheet!r3 | Y26 | same_period | Amortization!AD10 | Amortization!AD10 |
| Balance Sheet!AE9 | Balance Sheet\|9\|Balance Sheet!r3 | Y26 | same_period | CFS!AE25 | CFS!AE25 |
| Balance Sheet!AF10 | Balance Sheet\|10\|Balance Sheet!r3 | Y27 | aggregation | SUM(AF8:AF9) | Balance Sheet!AF8:AF9 |
| Balance Sheet!AF13 | Balance Sheet\|13\|Balance Sheet!r3 | Y27 | aggregation | SUM(Construction!$E$26:AE26) | Construction!E26:AE26 |
| Balance Sheet!AF14 | Balance Sheet\|14\|Balance Sheet!r3 | Y27 | rollforward | 'P&L'!AF25+CFS!AF21+'Balance Sheet'!AE14 | P&L!AF25, CFS!AF21, Balance Sheet!AE14 |
| Balance Sheet!AF15 | Balance Sheet\|15\|Balance Sheet!r3 | Y27 | same_period | Debt!AF11 | Debt!AF11 |
| Balance Sheet!AF16 | Balance Sheet\|16\|Balance Sheet!r3 | Y27 | aggregation | SUM(AF13:AF15) | Balance Sheet!AF13:AF15 |
| Balance Sheet!AF19 | Balance Sheet\|19\|Balance Sheet!r3 | Y27 | same_period | AF10-AF16<0.01 | Balance Sheet!AF10, Balance Sheet!AF16 |
| Balance Sheet!AF8 | Balance Sheet\|8\|Balance Sheet!r3 | Y27 | same_period | Amortization!AE10 | Amortization!AE10 |
| Balance Sheet!AF9 | Balance Sheet\|9\|Balance Sheet!r3 | Y27 | same_period | CFS!AF25 | CFS!AF25 |
| Balance Sheet!AG10 | Balance Sheet\|10\|Balance Sheet!r3 | Y28 | aggregation | SUM(AG8:AG9) | Balance Sheet!AG8:AG9 |
| Balance Sheet!AG13 | Balance Sheet\|13\|Balance Sheet!r3 | Y28 | aggregation | SUM(Construction!$E$26:AF26) | Construction!E26:AF26 |
| Balance Sheet!AG14 | Balance Sheet\|14\|Balance Sheet!r3 | Y28 | rollforward | 'P&L'!AG25+CFS!AG21+'Balance Sheet'!AF14 | P&L!AG25, CFS!AG21, Balance Sheet!AF14 |
| Balance Sheet!AG15 | Balance Sheet\|15\|Balance Sheet!r3 | Y28 | same_period | Debt!AG11 | Debt!AG11 |
| Balance Sheet!AG16 | Balance Sheet\|16\|Balance Sheet!r3 | Y28 | aggregation | SUM(AG13:AG15) | Balance Sheet!AG13:AG15 |
| Balance Sheet!AG19 | Balance Sheet\|19\|Balance Sheet!r3 | Y28 | same_period | AG10-AG16<0.01 | Balance Sheet!AG10, Balance Sheet!AG16 |
| Balance Sheet!AG8 | Balance Sheet\|8\|Balance Sheet!r3 | Y28 | same_period | Amortization!AF10 | Amortization!AF10 |
| Balance Sheet!AG9 | Balance Sheet\|9\|Balance Sheet!r3 | Y28 | same_period | CFS!AG25 | CFS!AG25 |
| Balance Sheet!AH10 | Balance Sheet\|10\|Balance Sheet!r3 | Y29 | aggregation | SUM(AH8:AH9) | Balance Sheet!AH8:AH9 |
| Balance Sheet!AH13 | Balance Sheet\|13\|Balance Sheet!r3 | Y29 | aggregation | SUM(Construction!$E$26:AG26) | Construction!E26:AG26 |
| Balance Sheet!AH14 | Balance Sheet\|14\|Balance Sheet!r3 | Y29 | rollforward | 'P&L'!AH25+CFS!AH21+'Balance Sheet'!AG14 | P&L!AH25, CFS!AH21, Balance Sheet!AG14 |
| Balance Sheet!AH15 | Balance Sheet\|15\|Balance Sheet!r3 | Y29 | same_period | Debt!AH11 | Debt!AH11 |
| Balance Sheet!AH16 | Balance Sheet\|16\|Balance Sheet!r3 | Y29 | aggregation | SUM(AH13:AH15) | Balance Sheet!AH13:AH15 |
| Balance Sheet!AH19 | Balance Sheet\|19\|Balance Sheet!r3 | Y29 | same_period | AH10-AH16<0.01 | Balance Sheet!AH10, Balance Sheet!AH16 |
| Balance Sheet!AH8 | Balance Sheet\|8\|Balance Sheet!r3 | Y29 | same_period | Amortization!AG10 | Amortization!AG10 |
| Balance Sheet!AH9 | Balance Sheet\|9\|Balance Sheet!r3 | Y29 | same_period | CFS!AH25 | CFS!AH25 |
| Balance Sheet!AI10 | Balance Sheet\|10\|Balance Sheet!r3 | Y30 | aggregation | SUM(AI8:AI9) | Balance Sheet!AI8:AI9 |
| Balance Sheet!AI13 | Balance Sheet\|13\|Balance Sheet!r3 | Y30 | aggregation | SUM(Construction!$E$26:AH26) | Construction!E26:AH26 |
| Balance Sheet!AI14 | Balance Sheet\|14\|Balance Sheet!r3 | Y30 | rollforward | 'P&L'!AI25+CFS!AI21+'Balance Sheet'!AH14 | P&L!AI25, CFS!AI21, Balance Sheet!AH14 |
| Balance Sheet!AI15 | Balance Sheet\|15\|Balance Sheet!r3 | Y30 | same_period | Debt!AI11 | Debt!AI11 |
| Balance Sheet!AI16 | Balance Sheet\|16\|Balance Sheet!r3 | Y30 | aggregation | SUM(AI13:AI15) | Balance Sheet!AI13:AI15 |
| Balance Sheet!AI19 | Balance Sheet\|19\|Balance Sheet!r3 | Y30 | same_period | AI10-AI16<0.01 | Balance Sheet!AI10, Balance Sheet!AI16 |
| Balance Sheet!AI8 | Balance Sheet\|8\|Balance Sheet!r3 | Y30 | same_period | Amortization!AH10 | Amortization!AH10 |
| Balance Sheet!AI9 | Balance Sheet\|9\|Balance Sheet!r3 | Y30 | same_period | CFS!AI25 | CFS!AI25 |
| Balance Sheet!AJ10 | Balance Sheet\|10\|Balance Sheet!r3 | Y31 | aggregation | SUM(AJ8:AJ9) | Balance Sheet!AJ8:AJ9 |
| Balance Sheet!AJ13 | Balance Sheet\|13\|Balance Sheet!r3 | Y31 | aggregation | SUM(Construction!$E$26:AI26) | Construction!E26:AI26 |
| Balance Sheet!AJ14 | Balance Sheet\|14\|Balance Sheet!r3 | Y31 | rollforward | 'P&L'!AJ25+CFS!AJ21+'Balance Sheet'!AI14 | P&L!AJ25, CFS!AJ21, Balance Sheet!AI14 |
| Balance Sheet!AJ15 | Balance Sheet\|15\|Balance Sheet!r3 | Y31 | same_period | Debt!AJ11 | Debt!AJ11 |
| Balance Sheet!AJ16 | Balance Sheet\|16\|Balance Sheet!r3 | Y31 | aggregation | SUM(AJ13:AJ15) | Balance Sheet!AJ13:AJ15 |
| Balance Sheet!AJ19 | Balance Sheet\|19\|Balance Sheet!r3 | Y31 | same_period | AJ10-AJ16<0.01 | Balance Sheet!AJ10, Balance Sheet!AJ16 |
| Balance Sheet!AJ8 | Balance Sheet\|8\|Balance Sheet!r3 | Y31 | same_period | Amortization!AI10 | Amortization!AI10 |
| Balance Sheet!AJ9 | Balance Sheet\|9\|Balance Sheet!r3 | Y31 | same_period | CFS!AJ25 | CFS!AJ25 |
| Balance Sheet!AK10 | Balance Sheet\|10\|Balance Sheet!r3 | Y32 | aggregation | SUM(AK8:AK9) | Balance Sheet!AK8:AK9 |
| Balance Sheet!AK13 | Balance Sheet\|13\|Balance Sheet!r3 | Y32 | aggregation | SUM(Construction!$E$26:AJ26) | Construction!E26:AJ26 |
| Balance Sheet!AK14 | Balance Sheet\|14\|Balance Sheet!r3 | Y32 | rollforward | 'P&L'!AK25+CFS!AK21+'Balance Sheet'!AJ14 | P&L!AK25, CFS!AK21, Balance Sheet!AJ14 |
| Balance Sheet!AK15 | Balance Sheet\|15\|Balance Sheet!r3 | Y32 | same_period | Debt!AK11 | Debt!AK11 |
| Balance Sheet!AK16 | Balance Sheet\|16\|Balance Sheet!r3 | Y32 | aggregation | SUM(AK13:AK15) | Balance Sheet!AK13:AK15 |
| Balance Sheet!AK19 | Balance Sheet\|19\|Balance Sheet!r3 | Y32 | same_period | AK10-AK16<0.01 | Balance Sheet!AK10, Balance Sheet!AK16 |
| Balance Sheet!AK8 | Balance Sheet\|8\|Balance Sheet!r3 | Y32 | same_period | Amortization!AJ10 | Amortization!AJ10 |
| Balance Sheet!AK9 | Balance Sheet\|9\|Balance Sheet!r3 | Y32 | same_period | CFS!AK25 | CFS!AK25 |
| Balance Sheet!AL10 | Balance Sheet\|10\|Balance Sheet!r3 | Y33 | aggregation | SUM(AL8:AL9) | Balance Sheet!AL8:AL9 |
| Balance Sheet!AL13 | Balance Sheet\|13\|Balance Sheet!r3 | Y33 | aggregation | SUM(Construction!$E$26:AK26) | Construction!E26:AK26 |
| Balance Sheet!AL14 | Balance Sheet\|14\|Balance Sheet!r3 | Y33 | rollforward | 'P&L'!AL25+CFS!AL21+'Balance Sheet'!AK14 | P&L!AL25, CFS!AL21, Balance Sheet!AK14 |
| Balance Sheet!AL15 | Balance Sheet\|15\|Balance Sheet!r3 | Y33 | same_period | Debt!AL11 | Debt!AL11 |
| Balance Sheet!AL16 | Balance Sheet\|16\|Balance Sheet!r3 | Y33 | aggregation | SUM(AL13:AL15) | Balance Sheet!AL13:AL15 |
| Balance Sheet!AL19 | Balance Sheet\|19\|Balance Sheet!r3 | Y33 | same_period | AL10-AL16<0.01 | Balance Sheet!AL10, Balance Sheet!AL16 |
| Balance Sheet!AL8 | Balance Sheet\|8\|Balance Sheet!r3 | Y33 | same_period | Amortization!AK10 | Amortization!AK10 |
| Balance Sheet!AL9 | Balance Sheet\|9\|Balance Sheet!r3 | Y33 | same_period | CFS!AL25 | CFS!AL25 |
| Balance Sheet!AM10 | Balance Sheet\|10\|Balance Sheet!r3 | Y34 | aggregation | SUM(AM8:AM9) | Balance Sheet!AM8:AM9 |
| Balance Sheet!AM13 | Balance Sheet\|13\|Balance Sheet!r3 | Y34 | aggregation | SUM(Construction!$E$26:AL26) | Construction!E26:AL26 |
| Balance Sheet!AM14 | Balance Sheet\|14\|Balance Sheet!r3 | Y34 | rollforward | 'P&L'!AM25+CFS!AM21+'Balance Sheet'!AL14 | P&L!AM25, CFS!AM21, Balance Sheet!AL14 |
| Balance Sheet!AM15 | Balance Sheet\|15\|Balance Sheet!r3 | Y34 | same_period | Debt!AM11 | Debt!AM11 |
| Balance Sheet!AM16 | Balance Sheet\|16\|Balance Sheet!r3 | Y34 | aggregation | SUM(AM13:AM15) | Balance Sheet!AM13:AM15 |
| Balance Sheet!AM19 | Balance Sheet\|19\|Balance Sheet!r3 | Y34 | same_period | AM10-AM16<0.01 | Balance Sheet!AM10, Balance Sheet!AM16 |
| Balance Sheet!AM8 | Balance Sheet\|8\|Balance Sheet!r3 | Y34 | same_period | Amortization!AL10 | Amortization!AL10 |
| Balance Sheet!AM9 | Balance Sheet\|9\|Balance Sheet!r3 | Y34 | same_period | CFS!AM25 | CFS!AM25 |
| Balance Sheet!AN10 | Balance Sheet\|10\|Balance Sheet!r3 | Y35 | aggregation | SUM(AN8:AN9) | Balance Sheet!AN8:AN9 |
| Balance Sheet!AN13 | Balance Sheet\|13\|Balance Sheet!r3 | Y35 | aggregation | SUM(Construction!$E$26:AM26) | Construction!E26:AM26 |
| Balance Sheet!AN14 | Balance Sheet\|14\|Balance Sheet!r3 | Y35 | rollforward | 'P&L'!AN25+CFS!AN21+'Balance Sheet'!AM14 | P&L!AN25, CFS!AN21, Balance Sheet!AM14 |
| Balance Sheet!AN15 | Balance Sheet\|15\|Balance Sheet!r3 | Y35 | same_period | Debt!AN11 | Debt!AN11 |
| Balance Sheet!AN16 | Balance Sheet\|16\|Balance Sheet!r3 | Y35 | aggregation | SUM(AN13:AN15) | Balance Sheet!AN13:AN15 |
| Balance Sheet!AN19 | Balance Sheet\|19\|Balance Sheet!r3 | Y35 | same_period | AN10-AN16<0.01 | Balance Sheet!AN10, Balance Sheet!AN16 |
| Balance Sheet!AN8 | Balance Sheet\|8\|Balance Sheet!r3 | Y35 | same_period | Amortization!AM10 | Amortization!AM10 |
| Balance Sheet!AN9 | Balance Sheet\|9\|Balance Sheet!r3 | Y35 | same_period | CFS!AN25 | CFS!AN25 |
| Balance Sheet!AO10 | Balance Sheet\|10\|Balance Sheet!r3 | Y36 | aggregation | SUM(AO8:AO9) | Balance Sheet!AO8:AO9 |
| Balance Sheet!AO13 | Balance Sheet\|13\|Balance Sheet!r3 | Y36 | aggregation | SUM(Construction!$E$26:AN26) | Construction!E26:AN26 |
| Balance Sheet!AO14 | Balance Sheet\|14\|Balance Sheet!r3 | Y36 | rollforward | 'P&L'!AO25+CFS!AO21+'Balance Sheet'!AN14 | P&L!AO25, CFS!AO21, Balance Sheet!AN14 |
| Balance Sheet!AO15 | Balance Sheet\|15\|Balance Sheet!r3 | Y36 | same_period | Debt!AO11 | Debt!AO11 |
| Balance Sheet!AO16 | Balance Sheet\|16\|Balance Sheet!r3 | Y36 | aggregation | SUM(AO13:AO15) | Balance Sheet!AO13:AO15 |
| Balance Sheet!AO19 | Balance Sheet\|19\|Balance Sheet!r3 | Y36 | same_period | AO10-AO16<0.01 | Balance Sheet!AO10, Balance Sheet!AO16 |
| Balance Sheet!AO8 | Balance Sheet\|8\|Balance Sheet!r3 | Y36 | same_period | Amortization!AN10 | Amortization!AN10 |
| Balance Sheet!AO9 | Balance Sheet\|9\|Balance Sheet!r3 | Y36 | same_period | CFS!AO25 | CFS!AO25 |
| Balance Sheet!AP10 | Balance Sheet\|10\|Balance Sheet!r3 | Y37 | aggregation | SUM(AP8:AP9) | Balance Sheet!AP8:AP9 |
| Balance Sheet!AP13 | Balance Sheet\|13\|Balance Sheet!r3 | Y37 | aggregation | SUM(Construction!$E$26:AO26) | Construction!E26:AO26 |
| Balance Sheet!AP14 | Balance Sheet\|14\|Balance Sheet!r3 | Y37 | rollforward | 'P&L'!AP25+CFS!AP21+'Balance Sheet'!AO14 | P&L!AP25, CFS!AP21, Balance Sheet!AO14 |
| Balance Sheet!AP15 | Balance Sheet\|15\|Balance Sheet!r3 | Y37 | same_period | Debt!AP11 | Debt!AP11 |
| Balance Sheet!AP16 | Balance Sheet\|16\|Balance Sheet!r3 | Y37 | aggregation | SUM(AP13:AP15) | Balance Sheet!AP13:AP15 |
| Balance Sheet!AP19 | Balance Sheet\|19\|Balance Sheet!r3 | Y37 | same_period | AP10-AP16<0.01 | Balance Sheet!AP10, Balance Sheet!AP16 |
| Balance Sheet!AP8 | Balance Sheet\|8\|Balance Sheet!r3 | Y37 | same_period | Amortization!AO10 | Amortization!AO10 |
| Balance Sheet!AP9 | Balance Sheet\|9\|Balance Sheet!r3 | Y37 | same_period | CFS!AP25 | CFS!AP25 |
| Balance Sheet!AQ10 | Balance Sheet\|10\|Balance Sheet!r3 | Y38 | aggregation | SUM(AQ8:AQ9) | Balance Sheet!AQ8:AQ9 |
| Balance Sheet!AQ13 | Balance Sheet\|13\|Balance Sheet!r3 | Y38 | aggregation | SUM(Construction!$E$26:AP26) | Construction!E26:AP26 |
| Balance Sheet!AQ14 | Balance Sheet\|14\|Balance Sheet!r3 | Y38 | rollforward | 'P&L'!AQ25+CFS!AQ21+'Balance Sheet'!AP14 | P&L!AQ25, CFS!AQ21, Balance Sheet!AP14 |
| Balance Sheet!AQ15 | Balance Sheet\|15\|Balance Sheet!r3 | Y38 | same_period | Debt!AQ11 | Debt!AQ11 |
| Balance Sheet!AQ16 | Balance Sheet\|16\|Balance Sheet!r3 | Y38 | aggregation | SUM(AQ13:AQ15) | Balance Sheet!AQ13:AQ15 |
| Balance Sheet!AQ19 | Balance Sheet\|19\|Balance Sheet!r3 | Y38 | same_period | AQ10-AQ16<0.01 | Balance Sheet!AQ10, Balance Sheet!AQ16 |
| Balance Sheet!AQ8 | Balance Sheet\|8\|Balance Sheet!r3 | Y38 | same_period | Amortization!AP10 | Amortization!AP10 |
| Balance Sheet!AQ9 | Balance Sheet\|9\|Balance Sheet!r3 | Y38 | same_period | CFS!AQ25 | CFS!AQ25 |
| Balance Sheet!AR10 | Balance Sheet\|10\|Balance Sheet!r3 | Y39 | aggregation | SUM(AR8:AR9) | Balance Sheet!AR8:AR9 |
| Balance Sheet!AR13 | Balance Sheet\|13\|Balance Sheet!r3 | Y39 | aggregation | SUM(Construction!$E$26:AQ26) | Construction!E26:AQ26 |
| Balance Sheet!AR14 | Balance Sheet\|14\|Balance Sheet!r3 | Y39 | rollforward | 'P&L'!AR25+CFS!AR21+'Balance Sheet'!AQ14 | P&L!AR25, CFS!AR21, Balance Sheet!AQ14 |
| Balance Sheet!AR15 | Balance Sheet\|15\|Balance Sheet!r3 | Y39 | same_period | Debt!AR11 | Debt!AR11 |
| Balance Sheet!AR16 | Balance Sheet\|16\|Balance Sheet!r3 | Y39 | aggregation | SUM(AR13:AR15) | Balance Sheet!AR13:AR15 |
| Balance Sheet!AR19 | Balance Sheet\|19\|Balance Sheet!r3 | Y39 | same_period | AR10-AR16<0.01 | Balance Sheet!AR10, Balance Sheet!AR16 |
| Balance Sheet!AR8 | Balance Sheet\|8\|Balance Sheet!r3 | Y39 | same_period | Amortization!AQ10 | Amortization!AQ10 |
| Balance Sheet!AR9 | Balance Sheet\|9\|Balance Sheet!r3 | Y39 | same_period | CFS!AR25 | CFS!AR25 |
| Balance Sheet!AS10 | Balance Sheet\|10\|Balance Sheet!r3 | Y40 | aggregation | SUM(AS8:AS9) | Balance Sheet!AS8:AS9 |
| Balance Sheet!AS13 | Balance Sheet\|13\|Balance Sheet!r3 | Y40 | aggregation | SUM(Construction!$E$26:AR26) | Construction!E26:AR26 |
| Balance Sheet!AS14 | Balance Sheet\|14\|Balance Sheet!r3 | Y40 | rollforward | 'P&L'!AS25+CFS!AS21+'Balance Sheet'!AR14 | P&L!AS25, CFS!AS21, Balance Sheet!AR14 |
| Balance Sheet!AS15 | Balance Sheet\|15\|Balance Sheet!r3 | Y40 | same_period | Debt!AS11 | Debt!AS11 |
| Balance Sheet!AS16 | Balance Sheet\|16\|Balance Sheet!r3 | Y40 | aggregation | SUM(AS13:AS15) | Balance Sheet!AS13:AS15 |
| Balance Sheet!AS19 | Balance Sheet\|19\|Balance Sheet!r3 | Y40 | same_period | AS10-AS16<0.01 | Balance Sheet!AS10, Balance Sheet!AS16 |
| Balance Sheet!AS8 | Balance Sheet\|8\|Balance Sheet!r3 | Y40 | same_period | Amortization!AR10 | Amortization!AR10 |
| Balance Sheet!AS9 | Balance Sheet\|9\|Balance Sheet!r3 | Y40 | same_period | CFS!AS25 | CFS!AS25 |
| Balance Sheet!F10 | Balance Sheet\|10\|Balance Sheet!r3 | Y1 | aggregation | SUM(F8:F9) | Balance Sheet!F8:F9 |
| Balance Sheet!F13 | Balance Sheet\|13\|Balance Sheet!r3 | Y1 | aggregation | SUM(Construction!$E$26:E26) | Construction!E26:E26 |
| Balance Sheet!F14 | Balance Sheet\|14\|Balance Sheet!r3 | Y1 | same_period | 'P&L'!F25+CFS!F21+'Balance Sheet'!E14 | P&L!F25, CFS!F21, Balance Sheet!E14 |
| Balance Sheet!F15 | Balance Sheet\|15\|Balance Sheet!r3 | Y1 | same_period | Debt!F11 | Debt!F11 |
| Balance Sheet!F16 | Balance Sheet\|16\|Balance Sheet!r3 | Y1 | aggregation | SUM(F13:F15) | Balance Sheet!F13:F15 |
| Balance Sheet!F19 | Balance Sheet\|19\|Balance Sheet!r3 | Y1 | same_period | F10-F16<0.01 | Balance Sheet!F10, Balance Sheet!F16 |
| Balance Sheet!F8 | Balance Sheet\|8\|Balance Sheet!r3 | Y1 | same_period | Amortization!E10 | Amortization!E10 |
| Balance Sheet!F9 | Balance Sheet\|9\|Balance Sheet!r3 | Y1 | same_period | CFS!F25 | CFS!F25 |
| Balance Sheet!G10 | Balance Sheet\|10\|Balance Sheet!r3 | Y2 | aggregation | SUM(G8:G9) | Balance Sheet!G8:G9 |
| Balance Sheet!G13 | Balance Sheet\|13\|Balance Sheet!r3 | Y2 | aggregation | SUM(Construction!$E$26:F26) | Construction!E26:F26 |
| Balance Sheet!G14 | Balance Sheet\|14\|Balance Sheet!r3 | Y2 | rollforward | 'P&L'!G25+CFS!G21+'Balance Sheet'!F14 | P&L!G25, CFS!G21, Balance Sheet!F14 |
| Balance Sheet!G15 | Balance Sheet\|15\|Balance Sheet!r3 | Y2 | same_period | Debt!G11 | Debt!G11 |
| Balance Sheet!G16 | Balance Sheet\|16\|Balance Sheet!r3 | Y2 | aggregation | SUM(G13:G15) | Balance Sheet!G13:G15 |
| Balance Sheet!G19 | Balance Sheet\|19\|Balance Sheet!r3 | Y2 | same_period | G10-G16<0.01 | Balance Sheet!G10, Balance Sheet!G16 |
| Balance Sheet!G8 | Balance Sheet\|8\|Balance Sheet!r3 | Y2 | same_period | Amortization!F10 | Amortization!F10 |
| Balance Sheet!G9 | Balance Sheet\|9\|Balance Sheet!r3 | Y2 | same_period | CFS!G25 | CFS!G25 |
| Balance Sheet!H10 | Balance Sheet\|10\|Balance Sheet!r3 | Y3 | aggregation | SUM(H8:H9) | Balance Sheet!H8:H9 |
| Balance Sheet!H13 | Balance Sheet\|13\|Balance Sheet!r3 | Y3 | aggregation | SUM(Construction!$E$26:G26) | Construction!E26:G26 |
| Balance Sheet!H14 | Balance Sheet\|14\|Balance Sheet!r3 | Y3 | rollforward | 'P&L'!H25+CFS!H21+'Balance Sheet'!G14 | P&L!H25, CFS!H21, Balance Sheet!G14 |
| Balance Sheet!H15 | Balance Sheet\|15\|Balance Sheet!r3 | Y3 | same_period | Debt!H11 | Debt!H11 |
| Balance Sheet!H16 | Balance Sheet\|16\|Balance Sheet!r3 | Y3 | aggregation | SUM(H13:H15) | Balance Sheet!H13:H15 |
| Balance Sheet!H19 | Balance Sheet\|19\|Balance Sheet!r3 | Y3 | same_period | H10-H16<0.01 | Balance Sheet!H10, Balance Sheet!H16 |
| Balance Sheet!H8 | Balance Sheet\|8\|Balance Sheet!r3 | Y3 | same_period | Amortization!G10 | Amortization!G10 |
| Balance Sheet!H9 | Balance Sheet\|9\|Balance Sheet!r3 | Y3 | same_period | CFS!H25 | CFS!H25 |
| Balance Sheet!I10 | Balance Sheet\|10\|Balance Sheet!r3 | Y4 | aggregation | SUM(I8:I9) | Balance Sheet!I8:I9 |
| Balance Sheet!I13 | Balance Sheet\|13\|Balance Sheet!r3 | Y4 | aggregation | SUM(Construction!$E$26:H26) | Construction!E26:H26 |
| Balance Sheet!I14 | Balance Sheet\|14\|Balance Sheet!r3 | Y4 | rollforward | 'P&L'!I25+CFS!I21+'Balance Sheet'!H14 | P&L!I25, CFS!I21, Balance Sheet!H14 |
| Balance Sheet!I15 | Balance Sheet\|15\|Balance Sheet!r3 | Y4 | same_period | Debt!I11 | Debt!I11 |
| Balance Sheet!I16 | Balance Sheet\|16\|Balance Sheet!r3 | Y4 | aggregation | SUM(I13:I15) | Balance Sheet!I13:I15 |
| Balance Sheet!I19 | Balance Sheet\|19\|Balance Sheet!r3 | Y4 | same_period | I10-I16<0.01 | Balance Sheet!I10, Balance Sheet!I16 |
| Balance Sheet!I8 | Balance Sheet\|8\|Balance Sheet!r3 | Y4 | same_period | Amortization!H10 | Amortization!H10 |
| Balance Sheet!I9 | Balance Sheet\|9\|Balance Sheet!r3 | Y4 | same_period | CFS!I25 | CFS!I25 |
| Balance Sheet!J10 | Balance Sheet\|10\|Balance Sheet!r3 | Y5 | aggregation | SUM(J8:J9) | Balance Sheet!J8:J9 |
| Balance Sheet!J13 | Balance Sheet\|13\|Balance Sheet!r3 | Y5 | aggregation | SUM(Construction!$E$26:I26) | Construction!E26:I26 |
| Balance Sheet!J14 | Balance Sheet\|14\|Balance Sheet!r3 | Y5 | rollforward | 'P&L'!J25+CFS!J21+'Balance Sheet'!I14 | P&L!J25, CFS!J21, Balance Sheet!I14 |
| Balance Sheet!J15 | Balance Sheet\|15\|Balance Sheet!r3 | Y5 | same_period | Debt!J11 | Debt!J11 |
| Balance Sheet!J16 | Balance Sheet\|16\|Balance Sheet!r3 | Y5 | aggregation | SUM(J13:J15) | Balance Sheet!J13:J15 |
| Balance Sheet!J19 | Balance Sheet\|19\|Balance Sheet!r3 | Y5 | same_period | J10-J16<0.01 | Balance Sheet!J10, Balance Sheet!J16 |
| Balance Sheet!J8 | Balance Sheet\|8\|Balance Sheet!r3 | Y5 | same_period | Amortization!I10 | Amortization!I10 |
| Balance Sheet!J9 | Balance Sheet\|9\|Balance Sheet!r3 | Y5 | same_period | CFS!J25 | CFS!J25 |
| Balance Sheet!K10 | Balance Sheet\|10\|Balance Sheet!r3 | Y6 | aggregation | SUM(K8:K9) | Balance Sheet!K8:K9 |
| Balance Sheet!K13 | Balance Sheet\|13\|Balance Sheet!r3 | Y6 | aggregation | SUM(Construction!$E$26:J26) | Construction!E26:J26 |
| Balance Sheet!K14 | Balance Sheet\|14\|Balance Sheet!r3 | Y6 | rollforward | 'P&L'!K25+CFS!K21+'Balance Sheet'!J14 | P&L!K25, CFS!K21, Balance Sheet!J14 |
| Balance Sheet!K15 | Balance Sheet\|15\|Balance Sheet!r3 | Y6 | same_period | Debt!K11 | Debt!K11 |
| Balance Sheet!K16 | Balance Sheet\|16\|Balance Sheet!r3 | Y6 | aggregation | SUM(K13:K15) | Balance Sheet!K13:K15 |
| Balance Sheet!K19 | Balance Sheet\|19\|Balance Sheet!r3 | Y6 | same_period | K10-K16<0.01 | Balance Sheet!K10, Balance Sheet!K16 |
| Balance Sheet!K8 | Balance Sheet\|8\|Balance Sheet!r3 | Y6 | same_period | Amortization!J10 | Amortization!J10 |
| Balance Sheet!K9 | Balance Sheet\|9\|Balance Sheet!r3 | Y6 | same_period | CFS!K25 | CFS!K25 |
| Balance Sheet!L10 | Balance Sheet\|10\|Balance Sheet!r3 | Y7 | aggregation | SUM(L8:L9) | Balance Sheet!L8:L9 |
| Balance Sheet!L13 | Balance Sheet\|13\|Balance Sheet!r3 | Y7 | aggregation | SUM(Construction!$E$26:K26) | Construction!E26:K26 |
| Balance Sheet!L14 | Balance Sheet\|14\|Balance Sheet!r3 | Y7 | rollforward | 'P&L'!L25+CFS!L21+'Balance Sheet'!K14 | P&L!L25, CFS!L21, Balance Sheet!K14 |
| Balance Sheet!L15 | Balance Sheet\|15\|Balance Sheet!r3 | Y7 | same_period | Debt!L11 | Debt!L11 |
| Balance Sheet!L16 | Balance Sheet\|16\|Balance Sheet!r3 | Y7 | aggregation | SUM(L13:L15) | Balance Sheet!L13:L15 |
| Balance Sheet!L19 | Balance Sheet\|19\|Balance Sheet!r3 | Y7 | same_period | L10-L16<0.01 | Balance Sheet!L10, Balance Sheet!L16 |
| Balance Sheet!L8 | Balance Sheet\|8\|Balance Sheet!r3 | Y7 | same_period | Amortization!K10 | Amortization!K10 |
| Balance Sheet!L9 | Balance Sheet\|9\|Balance Sheet!r3 | Y7 | same_period | CFS!L25 | CFS!L25 |
| Balance Sheet!M10 | Balance Sheet\|10\|Balance Sheet!r3 | Y8 | aggregation | SUM(M8:M9) | Balance Sheet!M8:M9 |
| Balance Sheet!M13 | Balance Sheet\|13\|Balance Sheet!r3 | Y8 | aggregation | SUM(Construction!$E$26:L26) | Construction!E26:L26 |
| Balance Sheet!M14 | Balance Sheet\|14\|Balance Sheet!r3 | Y8 | rollforward | 'P&L'!M25+CFS!M21+'Balance Sheet'!L14 | P&L!M25, CFS!M21, Balance Sheet!L14 |
| Balance Sheet!M15 | Balance Sheet\|15\|Balance Sheet!r3 | Y8 | same_period | Debt!M11 | Debt!M11 |
| Balance Sheet!M16 | Balance Sheet\|16\|Balance Sheet!r3 | Y8 | aggregation | SUM(M13:M15) | Balance Sheet!M13:M15 |
| Balance Sheet!M19 | Balance Sheet\|19\|Balance Sheet!r3 | Y8 | same_period | M10-M16<0.01 | Balance Sheet!M10, Balance Sheet!M16 |
| Balance Sheet!M8 | Balance Sheet\|8\|Balance Sheet!r3 | Y8 | same_period | Amortization!L10 | Amortization!L10 |
| Balance Sheet!M9 | Balance Sheet\|9\|Balance Sheet!r3 | Y8 | same_period | CFS!M25 | CFS!M25 |
| Balance Sheet!N10 | Balance Sheet\|10\|Balance Sheet!r3 | Y9 | aggregation | SUM(N8:N9) | Balance Sheet!N8:N9 |
| Balance Sheet!N13 | Balance Sheet\|13\|Balance Sheet!r3 | Y9 | aggregation | SUM(Construction!$E$26:M26) | Construction!E26:M26 |
| Balance Sheet!N14 | Balance Sheet\|14\|Balance Sheet!r3 | Y9 | rollforward | 'P&L'!N25+CFS!N21+'Balance Sheet'!M14 | P&L!N25, CFS!N21, Balance Sheet!M14 |
| Balance Sheet!N15 | Balance Sheet\|15\|Balance Sheet!r3 | Y9 | same_period | Debt!N11 | Debt!N11 |
| Balance Sheet!N16 | Balance Sheet\|16\|Balance Sheet!r3 | Y9 | aggregation | SUM(N13:N15) | Balance Sheet!N13:N15 |
| Balance Sheet!N19 | Balance Sheet\|19\|Balance Sheet!r3 | Y9 | same_period | N10-N16<0.01 | Balance Sheet!N10, Balance Sheet!N16 |
| Balance Sheet!N8 | Balance Sheet\|8\|Balance Sheet!r3 | Y9 | same_period | Amortization!M10 | Amortization!M10 |
| Balance Sheet!N9 | Balance Sheet\|9\|Balance Sheet!r3 | Y9 | same_period | CFS!N25 | CFS!N25 |
| Balance Sheet!O10 | Balance Sheet\|10\|Balance Sheet!r3 | Y10 | aggregation | SUM(O8:O9) | Balance Sheet!O8:O9 |
| Balance Sheet!O13 | Balance Sheet\|13\|Balance Sheet!r3 | Y10 | aggregation | SUM(Construction!$E$26:N26) | Construction!E26:N26 |
| Balance Sheet!O14 | Balance Sheet\|14\|Balance Sheet!r3 | Y10 | rollforward | 'P&L'!O25+CFS!O21+'Balance Sheet'!N14 | P&L!O25, CFS!O21, Balance Sheet!N14 |
| Balance Sheet!O15 | Balance Sheet\|15\|Balance Sheet!r3 | Y10 | same_period | Debt!O11 | Debt!O11 |
| Balance Sheet!O16 | Balance Sheet\|16\|Balance Sheet!r3 | Y10 | aggregation | SUM(O13:O15) | Balance Sheet!O13:O15 |
| Balance Sheet!O19 | Balance Sheet\|19\|Balance Sheet!r3 | Y10 | same_period | O10-O16<0.01 | Balance Sheet!O10, Balance Sheet!O16 |
| Balance Sheet!O8 | Balance Sheet\|8\|Balance Sheet!r3 | Y10 | same_period | Amortization!N10 | Amortization!N10 |
| Balance Sheet!O9 | Balance Sheet\|9\|Balance Sheet!r3 | Y10 | same_period | CFS!O25 | CFS!O25 |
| Balance Sheet!P10 | Balance Sheet\|10\|Balance Sheet!r3 | Y11 | aggregation | SUM(P8:P9) | Balance Sheet!P8:P9 |
| Balance Sheet!P13 | Balance Sheet\|13\|Balance Sheet!r3 | Y11 | aggregation | SUM(Construction!$E$26:O26) | Construction!E26:O26 |
| Balance Sheet!P14 | Balance Sheet\|14\|Balance Sheet!r3 | Y11 | rollforward | 'P&L'!P25+CFS!P21+'Balance Sheet'!O14 | P&L!P25, CFS!P21, Balance Sheet!O14 |
| Balance Sheet!P15 | Balance Sheet\|15\|Balance Sheet!r3 | Y11 | same_period | Debt!P11 | Debt!P11 |
| Balance Sheet!P16 | Balance Sheet\|16\|Balance Sheet!r3 | Y11 | aggregation | SUM(P13:P15) | Balance Sheet!P13:P15 |
| Balance Sheet!P19 | Balance Sheet\|19\|Balance Sheet!r3 | Y11 | same_period | P10-P16<0.01 | Balance Sheet!P10, Balance Sheet!P16 |
| Balance Sheet!P8 | Balance Sheet\|8\|Balance Sheet!r3 | Y11 | same_period | Amortization!O10 | Amortization!O10 |
| Balance Sheet!P9 | Balance Sheet\|9\|Balance Sheet!r3 | Y11 | same_period | CFS!P25 | CFS!P25 |
| Balance Sheet!Q10 | Balance Sheet\|10\|Balance Sheet!r3 | Y12 | aggregation | SUM(Q8:Q9) | Balance Sheet!Q8:Q9 |
| Balance Sheet!Q13 | Balance Sheet\|13\|Balance Sheet!r3 | Y12 | aggregation | SUM(Construction!$E$26:P26) | Construction!E26:P26 |
| Balance Sheet!Q14 | Balance Sheet\|14\|Balance Sheet!r3 | Y12 | rollforward | 'P&L'!Q25+CFS!Q21+'Balance Sheet'!P14 | P&L!Q25, CFS!Q21, Balance Sheet!P14 |
| Balance Sheet!Q15 | Balance Sheet\|15\|Balance Sheet!r3 | Y12 | same_period | Debt!Q11 | Debt!Q11 |
| Balance Sheet!Q16 | Balance Sheet\|16\|Balance Sheet!r3 | Y12 | aggregation | SUM(Q13:Q15) | Balance Sheet!Q13:Q15 |
| Balance Sheet!Q19 | Balance Sheet\|19\|Balance Sheet!r3 | Y12 | same_period | Q10-Q16<0.01 | Balance Sheet!Q10, Balance Sheet!Q16 |
| Balance Sheet!Q8 | Balance Sheet\|8\|Balance Sheet!r3 | Y12 | same_period | Amortization!P10 | Amortization!P10 |
| Balance Sheet!Q9 | Balance Sheet\|9\|Balance Sheet!r3 | Y12 | same_period | CFS!Q25 | CFS!Q25 |
| Balance Sheet!R10 | Balance Sheet\|10\|Balance Sheet!r3 | Y13 | aggregation | SUM(R8:R9) | Balance Sheet!R8:R9 |
| Balance Sheet!R13 | Balance Sheet\|13\|Balance Sheet!r3 | Y13 | aggregation | SUM(Construction!$E$26:Q26) | Construction!E26:Q26 |
| Balance Sheet!R14 | Balance Sheet\|14\|Balance Sheet!r3 | Y13 | rollforward | 'P&L'!R25+CFS!R21+'Balance Sheet'!Q14 | P&L!R25, CFS!R21, Balance Sheet!Q14 |
| Balance Sheet!R15 | Balance Sheet\|15\|Balance Sheet!r3 | Y13 | same_period | Debt!R11 | Debt!R11 |
| Balance Sheet!R16 | Balance Sheet\|16\|Balance Sheet!r3 | Y13 | aggregation | SUM(R13:R15) | Balance Sheet!R13:R15 |
| Balance Sheet!R19 | Balance Sheet\|19\|Balance Sheet!r3 | Y13 | same_period | R10-R16<0.01 | Balance Sheet!R10, Balance Sheet!R16 |
| Balance Sheet!R8 | Balance Sheet\|8\|Balance Sheet!r3 | Y13 | same_period | Amortization!Q10 | Amortization!Q10 |
| Balance Sheet!R9 | Balance Sheet\|9\|Balance Sheet!r3 | Y13 | same_period | CFS!R25 | CFS!R25 |
| Balance Sheet!S10 | Balance Sheet\|10\|Balance Sheet!r3 | Y14 | aggregation | SUM(S8:S9) | Balance Sheet!S8:S9 |
| Balance Sheet!S13 | Balance Sheet\|13\|Balance Sheet!r3 | Y14 | aggregation | SUM(Construction!$E$26:R26) | Construction!E26:R26 |
| Balance Sheet!S14 | Balance Sheet\|14\|Balance Sheet!r3 | Y14 | rollforward | 'P&L'!S25+CFS!S21+'Balance Sheet'!R14 | P&L!S25, CFS!S21, Balance Sheet!R14 |
| Balance Sheet!S15 | Balance Sheet\|15\|Balance Sheet!r3 | Y14 | same_period | Debt!S11 | Debt!S11 |
| Balance Sheet!S16 | Balance Sheet\|16\|Balance Sheet!r3 | Y14 | aggregation | SUM(S13:S15) | Balance Sheet!S13:S15 |
| Balance Sheet!S19 | Balance Sheet\|19\|Balance Sheet!r3 | Y14 | same_period | S10-S16<0.01 | Balance Sheet!S10, Balance Sheet!S16 |
| Balance Sheet!S8 | Balance Sheet\|8\|Balance Sheet!r3 | Y14 | same_period | Amortization!R10 | Amortization!R10 |
| Balance Sheet!S9 | Balance Sheet\|9\|Balance Sheet!r3 | Y14 | same_period | CFS!S25 | CFS!S25 |
| Balance Sheet!T10 | Balance Sheet\|10\|Balance Sheet!r3 | Y15 | aggregation | SUM(T8:T9) | Balance Sheet!T8:T9 |
| Balance Sheet!T13 | Balance Sheet\|13\|Balance Sheet!r3 | Y15 | aggregation | SUM(Construction!$E$26:S26) | Construction!E26:S26 |
| Balance Sheet!T14 | Balance Sheet\|14\|Balance Sheet!r3 | Y15 | rollforward | 'P&L'!T25+CFS!T21+'Balance Sheet'!S14 | P&L!T25, CFS!T21, Balance Sheet!S14 |
| Balance Sheet!T15 | Balance Sheet\|15\|Balance Sheet!r3 | Y15 | same_period | Debt!T11 | Debt!T11 |
| Balance Sheet!T16 | Balance Sheet\|16\|Balance Sheet!r3 | Y15 | aggregation | SUM(T13:T15) | Balance Sheet!T13:T15 |
| Balance Sheet!T19 | Balance Sheet\|19\|Balance Sheet!r3 | Y15 | same_period | T10-T16<0.01 | Balance Sheet!T10, Balance Sheet!T16 |
| Balance Sheet!T8 | Balance Sheet\|8\|Balance Sheet!r3 | Y15 | same_period | Amortization!S10 | Amortization!S10 |
| Balance Sheet!T9 | Balance Sheet\|9\|Balance Sheet!r3 | Y15 | same_period | CFS!T25 | CFS!T25 |
| Balance Sheet!U10 | Balance Sheet\|10\|Balance Sheet!r3 | Y16 | aggregation | SUM(U8:U9) | Balance Sheet!U8:U9 |
| Balance Sheet!U13 | Balance Sheet\|13\|Balance Sheet!r3 | Y16 | aggregation | SUM(Construction!$E$26:T26) | Construction!E26:T26 |
| Balance Sheet!U14 | Balance Sheet\|14\|Balance Sheet!r3 | Y16 | rollforward | 'P&L'!U25+CFS!U21+'Balance Sheet'!T14 | P&L!U25, CFS!U21, Balance Sheet!T14 |
| Balance Sheet!U15 | Balance Sheet\|15\|Balance Sheet!r3 | Y16 | same_period | Debt!U11 | Debt!U11 |
| Balance Sheet!U16 | Balance Sheet\|16\|Balance Sheet!r3 | Y16 | aggregation | SUM(U13:U15) | Balance Sheet!U13:U15 |
| Balance Sheet!U19 | Balance Sheet\|19\|Balance Sheet!r3 | Y16 | same_period | U10-U16<0.01 | Balance Sheet!U10, Balance Sheet!U16 |
| Balance Sheet!U8 | Balance Sheet\|8\|Balance Sheet!r3 | Y16 | same_period | Amortization!T10 | Amortization!T10 |
| Balance Sheet!U9 | Balance Sheet\|9\|Balance Sheet!r3 | Y16 | same_period | CFS!U25 | CFS!U25 |
| Balance Sheet!V10 | Balance Sheet\|10\|Balance Sheet!r3 | Y17 | aggregation | SUM(V8:V9) | Balance Sheet!V8:V9 |
| Balance Sheet!V13 | Balance Sheet\|13\|Balance Sheet!r3 | Y17 | aggregation | SUM(Construction!$E$26:U26) | Construction!E26:U26 |
| Balance Sheet!V14 | Balance Sheet\|14\|Balance Sheet!r3 | Y17 | rollforward | 'P&L'!V25+CFS!V21+'Balance Sheet'!U14 | P&L!V25, CFS!V21, Balance Sheet!U14 |
| Balance Sheet!V15 | Balance Sheet\|15\|Balance Sheet!r3 | Y17 | same_period | Debt!V11 | Debt!V11 |
| Balance Sheet!V16 | Balance Sheet\|16\|Balance Sheet!r3 | Y17 | aggregation | SUM(V13:V15) | Balance Sheet!V13:V15 |
| Balance Sheet!V19 | Balance Sheet\|19\|Balance Sheet!r3 | Y17 | same_period | V10-V16<0.01 | Balance Sheet!V10, Balance Sheet!V16 |
| Balance Sheet!V8 | Balance Sheet\|8\|Balance Sheet!r3 | Y17 | same_period | Amortization!U10 | Amortization!U10 |
| Balance Sheet!V9 | Balance Sheet\|9\|Balance Sheet!r3 | Y17 | same_period | CFS!V25 | CFS!V25 |
| Balance Sheet!W10 | Balance Sheet\|10\|Balance Sheet!r3 | Y18 | aggregation | SUM(W8:W9) | Balance Sheet!W8:W9 |
| Balance Sheet!W13 | Balance Sheet\|13\|Balance Sheet!r3 | Y18 | aggregation | SUM(Construction!$E$26:V26) | Construction!E26:V26 |
| Balance Sheet!W14 | Balance Sheet\|14\|Balance Sheet!r3 | Y18 | rollforward | 'P&L'!W25+CFS!W21+'Balance Sheet'!V14 | P&L!W25, CFS!W21, Balance Sheet!V14 |
| Balance Sheet!W15 | Balance Sheet\|15\|Balance Sheet!r3 | Y18 | same_period | Debt!W11 | Debt!W11 |
| Balance Sheet!W16 | Balance Sheet\|16\|Balance Sheet!r3 | Y18 | aggregation | SUM(W13:W15) | Balance Sheet!W13:W15 |
| Balance Sheet!W19 | Balance Sheet\|19\|Balance Sheet!r3 | Y18 | same_period | W10-W16<0.01 | Balance Sheet!W10, Balance Sheet!W16 |
| Balance Sheet!W8 | Balance Sheet\|8\|Balance Sheet!r3 | Y18 | same_period | Amortization!V10 | Amortization!V10 |
| Balance Sheet!W9 | Balance Sheet\|9\|Balance Sheet!r3 | Y18 | same_period | CFS!W25 | CFS!W25 |
| Balance Sheet!X10 | Balance Sheet\|10\|Balance Sheet!r3 | Y19 | aggregation | SUM(X8:X9) | Balance Sheet!X8:X9 |
| Balance Sheet!X13 | Balance Sheet\|13\|Balance Sheet!r3 | Y19 | aggregation | SUM(Construction!$E$26:W26) | Construction!E26:W26 |
| Balance Sheet!X14 | Balance Sheet\|14\|Balance Sheet!r3 | Y19 | rollforward | 'P&L'!X25+CFS!X21+'Balance Sheet'!W14 | P&L!X25, CFS!X21, Balance Sheet!W14 |
| Balance Sheet!X15 | Balance Sheet\|15\|Balance Sheet!r3 | Y19 | same_period | Debt!X11 | Debt!X11 |
| Balance Sheet!X16 | Balance Sheet\|16\|Balance Sheet!r3 | Y19 | aggregation | SUM(X13:X15) | Balance Sheet!X13:X15 |
| Balance Sheet!X19 | Balance Sheet\|19\|Balance Sheet!r3 | Y19 | same_period | X10-X16<0.01 | Balance Sheet!X10, Balance Sheet!X16 |
| Balance Sheet!X8 | Balance Sheet\|8\|Balance Sheet!r3 | Y19 | same_period | Amortization!W10 | Amortization!W10 |
| Balance Sheet!X9 | Balance Sheet\|9\|Balance Sheet!r3 | Y19 | same_period | CFS!X25 | CFS!X25 |
| Balance Sheet!Y10 | Balance Sheet\|10\|Balance Sheet!r3 | Y20 | aggregation | SUM(Y8:Y9) | Balance Sheet!Y8:Y9 |
| Balance Sheet!Y13 | Balance Sheet\|13\|Balance Sheet!r3 | Y20 | aggregation | SUM(Construction!$E$26:X26) | Construction!E26:X26 |
| Balance Sheet!Y14 | Balance Sheet\|14\|Balance Sheet!r3 | Y20 | rollforward | 'P&L'!Y25+CFS!Y21+'Balance Sheet'!X14 | P&L!Y25, CFS!Y21, Balance Sheet!X14 |
| Balance Sheet!Y15 | Balance Sheet\|15\|Balance Sheet!r3 | Y20 | same_period | Debt!Y11 | Debt!Y11 |
| Balance Sheet!Y16 | Balance Sheet\|16\|Balance Sheet!r3 | Y20 | aggregation | SUM(Y13:Y15) | Balance Sheet!Y13:Y15 |
| Balance Sheet!Y19 | Balance Sheet\|19\|Balance Sheet!r3 | Y20 | same_period | Y10-Y16<0.01 | Balance Sheet!Y10, Balance Sheet!Y16 |
| Balance Sheet!Y8 | Balance Sheet\|8\|Balance Sheet!r3 | Y20 | same_period | Amortization!X10 | Amortization!X10 |
| Balance Sheet!Y9 | Balance Sheet\|9\|Balance Sheet!r3 | Y20 | same_period | CFS!Y25 | CFS!Y25 |
| Balance Sheet!Z10 | Balance Sheet\|10\|Balance Sheet!r3 | Y21 | aggregation | SUM(Z8:Z9) | Balance Sheet!Z8:Z9 |
| Balance Sheet!Z13 | Balance Sheet\|13\|Balance Sheet!r3 | Y21 | aggregation | SUM(Construction!$E$26:Y26) | Construction!E26:Y26 |
| Balance Sheet!Z14 | Balance Sheet\|14\|Balance Sheet!r3 | Y21 | rollforward | 'P&L'!Z25+CFS!Z21+'Balance Sheet'!Y14 | P&L!Z25, CFS!Z21, Balance Sheet!Y14 |
| Balance Sheet!Z15 | Balance Sheet\|15\|Balance Sheet!r3 | Y21 | same_period | Debt!Z11 | Debt!Z11 |
| Balance Sheet!Z16 | Balance Sheet\|16\|Balance Sheet!r3 | Y21 | aggregation | SUM(Z13:Z15) | Balance Sheet!Z13:Z15 |
| Balance Sheet!Z19 | Balance Sheet\|19\|Balance Sheet!r3 | Y21 | same_period | Z10-Z16<0.01 | Balance Sheet!Z10, Balance Sheet!Z16 |
| Balance Sheet!Z8 | Balance Sheet\|8\|Balance Sheet!r3 | Y21 | same_period | Amortization!Y10 | Amortization!Y10 |
| Balance Sheet!Z9 | Balance Sheet\|9\|Balance Sheet!r3 | Y21 | same_period | CFS!Z25 | CFS!Z25 |
| CFS!AA10 | CFS\|10\|CFS!r3 | Y22 | same_period | -Operation!Z21 | Operation!Z21 |
| CFS!AA12 | CFS\|12\|CFS!r3 | Y22 | same_period | 'P&L'!AA23 | P&L!AA23 |
| CFS!AA14 | CFS\|14\|CFS!r3 | Y22 | aggregation | SUM(AA8:AA13) | CFS!AA8:AA13 |
| CFS!AA16 | CFS\|16\|CFS!r3 | Y22 | same_period | Debt!AA14 | Debt!AA14 |
| CFS!AA17 | CFS\|17\|CFS!r3 | Y22 | same_period | Debt!AA10 | Debt!AA10 |
| CFS!AA19 | CFS\|19\|CFS!r3 | Y22 | same_period | AA14+AA16+AA17 | CFS!AA14, CFS!AA16, CFS!AA17 |
| CFS!AA21 | CFS\|21\|CFS!r3 | Y22 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AA25,0),MAX(AA19+Z25,0)) | Input Assumptions!D45, P&L!AA25, CFS!AA19, CFS!Z25 |
| CFS!AA23 | CFS\|23\|CFS!r3 | Y22 | same_period | AA19+AA21 | CFS!AA19, CFS!AA21 |
| CFS!AA25 | CFS\|25\|CFS!r3 | Y22 | rollforward | Z25+AA23 | CFS!Z25, CFS!AA23 |
| CFS!AA8 | CFS\|8\|CFS!r3 | Y22 | same_period | Operation!Z14 | Operation!Z14 |
| CFS!AB10 | CFS\|10\|CFS!r3 | Y23 | same_period | -Operation!AA21 | Operation!AA21 |
| CFS!AB12 | CFS\|12\|CFS!r3 | Y23 | same_period | 'P&L'!AB23 | P&L!AB23 |
| CFS!AB14 | CFS\|14\|CFS!r3 | Y23 | aggregation | SUM(AB8:AB13) | CFS!AB8:AB13 |
| CFS!AB16 | CFS\|16\|CFS!r3 | Y23 | same_period | Debt!AB14 | Debt!AB14 |
| CFS!AB17 | CFS\|17\|CFS!r3 | Y23 | same_period | Debt!AB10 | Debt!AB10 |
| CFS!AB19 | CFS\|19\|CFS!r3 | Y23 | same_period | AB14+AB16+AB17 | CFS!AB14, CFS!AB16, CFS!AB17 |
| CFS!AB21 | CFS\|21\|CFS!r3 | Y23 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AB25,0),MAX(AB19+AA25,0)) | Input Assumptions!D45, P&L!AB25, CFS!AB19, CFS!AA25 |
| CFS!AB23 | CFS\|23\|CFS!r3 | Y23 | same_period | AB19+AB21 | CFS!AB19, CFS!AB21 |
| CFS!AB25 | CFS\|25\|CFS!r3 | Y23 | rollforward | AA25+AB23 | CFS!AA25, CFS!AB23 |
| CFS!AB8 | CFS\|8\|CFS!r3 | Y23 | same_period | Operation!AA14 | Operation!AA14 |
| CFS!AC10 | CFS\|10\|CFS!r3 | Y24 | same_period | -Operation!AB21 | Operation!AB21 |
| CFS!AC12 | CFS\|12\|CFS!r3 | Y24 | same_period | 'P&L'!AC23 | P&L!AC23 |
| CFS!AC14 | CFS\|14\|CFS!r3 | Y24 | aggregation | SUM(AC8:AC13) | CFS!AC8:AC13 |
| CFS!AC16 | CFS\|16\|CFS!r3 | Y24 | same_period | Debt!AC14 | Debt!AC14 |
| CFS!AC17 | CFS\|17\|CFS!r3 | Y24 | same_period | Debt!AC10 | Debt!AC10 |
| CFS!AC19 | CFS\|19\|CFS!r3 | Y24 | same_period | AC14+AC16+AC17 | CFS!AC14, CFS!AC16, CFS!AC17 |
| CFS!AC21 | CFS\|21\|CFS!r3 | Y24 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AC25,0),MAX(AC19+AB25,0)) | Input Assumptions!D45, P&L!AC25, CFS!AC19, CFS!AB25 |
| CFS!AC23 | CFS\|23\|CFS!r3 | Y24 | same_period | AC19+AC21 | CFS!AC19, CFS!AC21 |
| CFS!AC25 | CFS\|25\|CFS!r3 | Y24 | rollforward | AB25+AC23 | CFS!AB25, CFS!AC23 |
| CFS!AC8 | CFS\|8\|CFS!r3 | Y24 | same_period | Operation!AB14 | Operation!AB14 |
| CFS!AD10 | CFS\|10\|CFS!r3 | Y25 | same_period | -Operation!AC21 | Operation!AC21 |
| CFS!AD12 | CFS\|12\|CFS!r3 | Y25 | same_period | 'P&L'!AD23 | P&L!AD23 |
| CFS!AD14 | CFS\|14\|CFS!r3 | Y25 | aggregation | SUM(AD8:AD13) | CFS!AD8:AD13 |
| CFS!AD16 | CFS\|16\|CFS!r3 | Y25 | same_period | Debt!AD14 | Debt!AD14 |
| CFS!AD17 | CFS\|17\|CFS!r3 | Y25 | same_period | Debt!AD10 | Debt!AD10 |
| CFS!AD19 | CFS\|19\|CFS!r3 | Y25 | same_period | AD14+AD16+AD17 | CFS!AD14, CFS!AD16, CFS!AD17 |
| CFS!AD21 | CFS\|21\|CFS!r3 | Y25 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AD25,0),MAX(AD19+AC25,0)) | Input Assumptions!D45, P&L!AD25, CFS!AD19, CFS!AC25 |
| CFS!AD23 | CFS\|23\|CFS!r3 | Y25 | same_period | AD19+AD21 | CFS!AD19, CFS!AD21 |
| CFS!AD25 | CFS\|25\|CFS!r3 | Y25 | rollforward | AC25+AD23 | CFS!AC25, CFS!AD23 |
| CFS!AD8 | CFS\|8\|CFS!r3 | Y25 | same_period | Operation!AC14 | Operation!AC14 |
| CFS!AE10 | CFS\|10\|CFS!r3 | Y26 | same_period | -Operation!AD21 | Operation!AD21 |
| CFS!AE12 | CFS\|12\|CFS!r3 | Y26 | same_period | 'P&L'!AE23 | P&L!AE23 |
| CFS!AE14 | CFS\|14\|CFS!r3 | Y26 | aggregation | SUM(AE8:AE13) | CFS!AE8:AE13 |
| CFS!AE16 | CFS\|16\|CFS!r3 | Y26 | same_period | Debt!AE14 | Debt!AE14 |
| CFS!AE17 | CFS\|17\|CFS!r3 | Y26 | same_period | Debt!AE10 | Debt!AE10 |
| CFS!AE19 | CFS\|19\|CFS!r3 | Y26 | same_period | AE14+AE16+AE17 | CFS!AE14, CFS!AE16, CFS!AE17 |
| CFS!AE21 | CFS\|21\|CFS!r3 | Y26 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AE25,0),MAX(AE19+AD25,0)) | Input Assumptions!D45, P&L!AE25, CFS!AE19, CFS!AD25 |
| CFS!AE23 | CFS\|23\|CFS!r3 | Y26 | same_period | AE19+AE21 | CFS!AE19, CFS!AE21 |
| CFS!AE25 | CFS\|25\|CFS!r3 | Y26 | rollforward | AD25+AE23 | CFS!AD25, CFS!AE23 |
| CFS!AE8 | CFS\|8\|CFS!r3 | Y26 | same_period | Operation!AD14 | Operation!AD14 |
| CFS!AF10 | CFS\|10\|CFS!r3 | Y27 | same_period | -Operation!AE21 | Operation!AE21 |
| CFS!AF12 | CFS\|12\|CFS!r3 | Y27 | same_period | 'P&L'!AF23 | P&L!AF23 |
| CFS!AF14 | CFS\|14\|CFS!r3 | Y27 | aggregation | SUM(AF8:AF13) | CFS!AF8:AF13 |
| CFS!AF16 | CFS\|16\|CFS!r3 | Y27 | same_period | Debt!AF14 | Debt!AF14 |
| CFS!AF17 | CFS\|17\|CFS!r3 | Y27 | same_period | Debt!AF10 | Debt!AF10 |
| CFS!AF19 | CFS\|19\|CFS!r3 | Y27 | same_period | AF14+AF16+AF17 | CFS!AF14, CFS!AF16, CFS!AF17 |
| CFS!AF21 | CFS\|21\|CFS!r3 | Y27 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AF25,0),MAX(AF19+AE25,0)) | Input Assumptions!D45, P&L!AF25, CFS!AF19, CFS!AE25 |
| CFS!AF23 | CFS\|23\|CFS!r3 | Y27 | same_period | AF19+AF21 | CFS!AF19, CFS!AF21 |
| CFS!AF25 | CFS\|25\|CFS!r3 | Y27 | rollforward | AE25+AF23 | CFS!AE25, CFS!AF23 |
| CFS!AF8 | CFS\|8\|CFS!r3 | Y27 | same_period | Operation!AE14 | Operation!AE14 |
| CFS!AG10 | CFS\|10\|CFS!r3 | Y28 | same_period | -Operation!AF21 | Operation!AF21 |
| CFS!AG12 | CFS\|12\|CFS!r3 | Y28 | same_period | 'P&L'!AG23 | P&L!AG23 |
| CFS!AG14 | CFS\|14\|CFS!r3 | Y28 | aggregation | SUM(AG8:AG13) | CFS!AG8:AG13 |
| CFS!AG16 | CFS\|16\|CFS!r3 | Y28 | same_period | Debt!AG14 | Debt!AG14 |
| CFS!AG17 | CFS\|17\|CFS!r3 | Y28 | same_period | Debt!AG10 | Debt!AG10 |
| CFS!AG19 | CFS\|19\|CFS!r3 | Y28 | same_period | AG14+AG16+AG17 | CFS!AG14, CFS!AG16, CFS!AG17 |
| CFS!AG21 | CFS\|21\|CFS!r3 | Y28 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AG25,0),MAX(AG19+AF25,0)) | Input Assumptions!D45, P&L!AG25, CFS!AG19, CFS!AF25 |
| CFS!AG23 | CFS\|23\|CFS!r3 | Y28 | same_period | AG19+AG21 | CFS!AG19, CFS!AG21 |
| CFS!AG25 | CFS\|25\|CFS!r3 | Y28 | rollforward | AF25+AG23 | CFS!AF25, CFS!AG23 |
| CFS!AG8 | CFS\|8\|CFS!r3 | Y28 | same_period | Operation!AF14 | Operation!AF14 |
| CFS!AH10 | CFS\|10\|CFS!r3 | Y29 | same_period | -Operation!AG21 | Operation!AG21 |
| CFS!AH12 | CFS\|12\|CFS!r3 | Y29 | same_period | 'P&L'!AH23 | P&L!AH23 |
| CFS!AH14 | CFS\|14\|CFS!r3 | Y29 | aggregation | SUM(AH8:AH13) | CFS!AH8:AH13 |
| CFS!AH16 | CFS\|16\|CFS!r3 | Y29 | same_period | Debt!AH14 | Debt!AH14 |
| CFS!AH17 | CFS\|17\|CFS!r3 | Y29 | same_period | Debt!AH10 | Debt!AH10 |
| CFS!AH19 | CFS\|19\|CFS!r3 | Y29 | same_period | AH14+AH16+AH17 | CFS!AH14, CFS!AH16, CFS!AH17 |
| CFS!AH21 | CFS\|21\|CFS!r3 | Y29 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AH25,0),MAX(AH19+AG25,0)) | Input Assumptions!D45, P&L!AH25, CFS!AH19, CFS!AG25 |
| CFS!AH23 | CFS\|23\|CFS!r3 | Y29 | same_period | AH19+AH21 | CFS!AH19, CFS!AH21 |
| CFS!AH25 | CFS\|25\|CFS!r3 | Y29 | rollforward | AG25+AH23 | CFS!AG25, CFS!AH23 |
| CFS!AH8 | CFS\|8\|CFS!r3 | Y29 | same_period | Operation!AG14 | Operation!AG14 |
| CFS!AI10 | CFS\|10\|CFS!r3 | Y30 | same_period | -Operation!AH21 | Operation!AH21 |
| CFS!AI12 | CFS\|12\|CFS!r3 | Y30 | same_period | 'P&L'!AI23 | P&L!AI23 |
| CFS!AI14 | CFS\|14\|CFS!r3 | Y30 | aggregation | SUM(AI8:AI13) | CFS!AI8:AI13 |
| CFS!AI16 | CFS\|16\|CFS!r3 | Y30 | same_period | Debt!AI14 | Debt!AI14 |
| CFS!AI17 | CFS\|17\|CFS!r3 | Y30 | same_period | Debt!AI10 | Debt!AI10 |
| CFS!AI19 | CFS\|19\|CFS!r3 | Y30 | same_period | AI14+AI16+AI17 | CFS!AI14, CFS!AI16, CFS!AI17 |
| CFS!AI21 | CFS\|21\|CFS!r3 | Y30 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AI25,0),MAX(AI19+AH25,0)) | Input Assumptions!D45, P&L!AI25, CFS!AI19, CFS!AH25 |
| CFS!AI23 | CFS\|23\|CFS!r3 | Y30 | same_period | AI19+AI21 | CFS!AI19, CFS!AI21 |
| CFS!AI25 | CFS\|25\|CFS!r3 | Y30 | rollforward | AH25+AI23 | CFS!AH25, CFS!AI23 |
| CFS!AI8 | CFS\|8\|CFS!r3 | Y30 | same_period | Operation!AH14 | Operation!AH14 |
| CFS!AJ10 | CFS\|10\|CFS!r3 | Y31 | same_period | -Operation!AI21 | Operation!AI21 |
| CFS!AJ12 | CFS\|12\|CFS!r3 | Y31 | same_period | 'P&L'!AJ23 | P&L!AJ23 |
| CFS!AJ14 | CFS\|14\|CFS!r3 | Y31 | aggregation | SUM(AJ8:AJ13) | CFS!AJ8:AJ13 |
| CFS!AJ16 | CFS\|16\|CFS!r3 | Y31 | same_period | Debt!AJ14 | Debt!AJ14 |
| CFS!AJ17 | CFS\|17\|CFS!r3 | Y31 | same_period | Debt!AJ10 | Debt!AJ10 |
| CFS!AJ19 | CFS\|19\|CFS!r3 | Y31 | same_period | AJ14+AJ16+AJ17 | CFS!AJ14, CFS!AJ16, CFS!AJ17 |
| CFS!AJ21 | CFS\|21\|CFS!r3 | Y31 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AJ25,0),MAX(AJ19+AI25,0)) | Input Assumptions!D45, P&L!AJ25, CFS!AJ19, CFS!AI25 |
| CFS!AJ23 | CFS\|23\|CFS!r3 | Y31 | same_period | AJ19+AJ21 | CFS!AJ19, CFS!AJ21 |
| CFS!AJ25 | CFS\|25\|CFS!r3 | Y31 | rollforward | AI25+AJ23 | CFS!AI25, CFS!AJ23 |
| CFS!AJ8 | CFS\|8\|CFS!r3 | Y31 | same_period | Operation!AI14 | Operation!AI14 |
| CFS!AK10 | CFS\|10\|CFS!r3 | Y32 | same_period | -Operation!AJ21 | Operation!AJ21 |
| CFS!AK12 | CFS\|12\|CFS!r3 | Y32 | same_period | 'P&L'!AK23 | P&L!AK23 |
| CFS!AK14 | CFS\|14\|CFS!r3 | Y32 | aggregation | SUM(AK8:AK13) | CFS!AK8:AK13 |
| CFS!AK16 | CFS\|16\|CFS!r3 | Y32 | same_period | Debt!AK14 | Debt!AK14 |
| CFS!AK17 | CFS\|17\|CFS!r3 | Y32 | same_period | Debt!AK10 | Debt!AK10 |
| CFS!AK19 | CFS\|19\|CFS!r3 | Y32 | same_period | AK14+AK16+AK17 | CFS!AK14, CFS!AK16, CFS!AK17 |
| CFS!AK21 | CFS\|21\|CFS!r3 | Y32 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AK25,0),MAX(AK19+AJ25,0)) | Input Assumptions!D45, P&L!AK25, CFS!AK19, CFS!AJ25 |
| CFS!AK23 | CFS\|23\|CFS!r3 | Y32 | same_period | AK19+AK21 | CFS!AK19, CFS!AK21 |
| CFS!AK25 | CFS\|25\|CFS!r3 | Y32 | rollforward | AJ25+AK23 | CFS!AJ25, CFS!AK23 |
| CFS!AK8 | CFS\|8\|CFS!r3 | Y32 | same_period | Operation!AJ14 | Operation!AJ14 |
| CFS!AL10 | CFS\|10\|CFS!r3 | Y33 | same_period | -Operation!AK21 | Operation!AK21 |
| CFS!AL12 | CFS\|12\|CFS!r3 | Y33 | same_period | 'P&L'!AL23 | P&L!AL23 |
| CFS!AL14 | CFS\|14\|CFS!r3 | Y33 | aggregation | SUM(AL8:AL13) | CFS!AL8:AL13 |
| CFS!AL16 | CFS\|16\|CFS!r3 | Y33 | same_period | Debt!AL14 | Debt!AL14 |
| CFS!AL17 | CFS\|17\|CFS!r3 | Y33 | same_period | Debt!AL10 | Debt!AL10 |
| CFS!AL19 | CFS\|19\|CFS!r3 | Y33 | same_period | AL14+AL16+AL17 | CFS!AL14, CFS!AL16, CFS!AL17 |
| CFS!AL21 | CFS\|21\|CFS!r3 | Y33 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AL25,0),MAX(AL19+AK25,0)) | Input Assumptions!D45, P&L!AL25, CFS!AL19, CFS!AK25 |
| CFS!AL23 | CFS\|23\|CFS!r3 | Y33 | same_period | AL19+AL21 | CFS!AL19, CFS!AL21 |
| CFS!AL25 | CFS\|25\|CFS!r3 | Y33 | rollforward | AK25+AL23 | CFS!AK25, CFS!AL23 |
| CFS!AL8 | CFS\|8\|CFS!r3 | Y33 | same_period | Operation!AK14 | Operation!AK14 |
| CFS!AM10 | CFS\|10\|CFS!r3 | Y34 | same_period | -Operation!AL21 | Operation!AL21 |
| CFS!AM12 | CFS\|12\|CFS!r3 | Y34 | same_period | 'P&L'!AM23 | P&L!AM23 |
| CFS!AM14 | CFS\|14\|CFS!r3 | Y34 | aggregation | SUM(AM8:AM13) | CFS!AM8:AM13 |
| CFS!AM16 | CFS\|16\|CFS!r3 | Y34 | same_period | Debt!AM14 | Debt!AM14 |
| CFS!AM17 | CFS\|17\|CFS!r3 | Y34 | same_period | Debt!AM10 | Debt!AM10 |
| CFS!AM19 | CFS\|19\|CFS!r3 | Y34 | same_period | AM14+AM16+AM17 | CFS!AM14, CFS!AM16, CFS!AM17 |
| CFS!AM21 | CFS\|21\|CFS!r3 | Y34 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AM25,0),MAX(AM19+AL25,0)) | Input Assumptions!D45, P&L!AM25, CFS!AM19, CFS!AL25 |
| CFS!AM23 | CFS\|23\|CFS!r3 | Y34 | same_period | AM19+AM21 | CFS!AM19, CFS!AM21 |
| CFS!AM25 | CFS\|25\|CFS!r3 | Y34 | rollforward | AL25+AM23 | CFS!AL25, CFS!AM23 |
| CFS!AM8 | CFS\|8\|CFS!r3 | Y34 | same_period | Operation!AL14 | Operation!AL14 |
| CFS!AN10 | CFS\|10\|CFS!r3 | Y35 | same_period | -Operation!AM21 | Operation!AM21 |
| CFS!AN12 | CFS\|12\|CFS!r3 | Y35 | same_period | 'P&L'!AN23 | P&L!AN23 |
| CFS!AN14 | CFS\|14\|CFS!r3 | Y35 | aggregation | SUM(AN8:AN13) | CFS!AN8:AN13 |
| CFS!AN16 | CFS\|16\|CFS!r3 | Y35 | same_period | Debt!AN14 | Debt!AN14 |
| CFS!AN17 | CFS\|17\|CFS!r3 | Y35 | same_period | Debt!AN10 | Debt!AN10 |
| CFS!AN19 | CFS\|19\|CFS!r3 | Y35 | same_period | AN14+AN16+AN17 | CFS!AN14, CFS!AN16, CFS!AN17 |
| CFS!AN21 | CFS\|21\|CFS!r3 | Y35 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AN25,0),MAX(AN19+AM25,0)) | Input Assumptions!D45, P&L!AN25, CFS!AN19, CFS!AM25 |
| CFS!AN23 | CFS\|23\|CFS!r3 | Y35 | same_period | AN19+AN21 | CFS!AN19, CFS!AN21 |
| CFS!AN25 | CFS\|25\|CFS!r3 | Y35 | rollforward | AM25+AN23 | CFS!AM25, CFS!AN23 |
| CFS!AN8 | CFS\|8\|CFS!r3 | Y35 | same_period | Operation!AM14 | Operation!AM14 |
| CFS!AO10 | CFS\|10\|CFS!r3 | Y36 | same_period | -Operation!AN21 | Operation!AN21 |
| CFS!AO12 | CFS\|12\|CFS!r3 | Y36 | same_period | 'P&L'!AO23 | P&L!AO23 |
| CFS!AO14 | CFS\|14\|CFS!r3 | Y36 | aggregation | SUM(AO8:AO13) | CFS!AO8:AO13 |
| CFS!AO16 | CFS\|16\|CFS!r3 | Y36 | same_period | Debt!AO14 | Debt!AO14 |
| CFS!AO17 | CFS\|17\|CFS!r3 | Y36 | same_period | Debt!AO10 | Debt!AO10 |
| CFS!AO19 | CFS\|19\|CFS!r3 | Y36 | same_period | AO14+AO16+AO17 | CFS!AO14, CFS!AO16, CFS!AO17 |
| CFS!AO21 | CFS\|21\|CFS!r3 | Y36 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AO25,0),MAX(AO19+AN25,0)) | Input Assumptions!D45, P&L!AO25, CFS!AO19, CFS!AN25 |
| CFS!AO23 | CFS\|23\|CFS!r3 | Y36 | same_period | AO19+AO21 | CFS!AO19, CFS!AO21 |
| CFS!AO25 | CFS\|25\|CFS!r3 | Y36 | rollforward | AN25+AO23 | CFS!AN25, CFS!AO23 |
| CFS!AO8 | CFS\|8\|CFS!r3 | Y36 | same_period | Operation!AN14 | Operation!AN14 |
| CFS!AP10 | CFS\|10\|CFS!r3 | Y37 | same_period | -Operation!AO21 | Operation!AO21 |
| CFS!AP12 | CFS\|12\|CFS!r3 | Y37 | same_period | 'P&L'!AP23 | P&L!AP23 |
| CFS!AP14 | CFS\|14\|CFS!r3 | Y37 | aggregation | SUM(AP8:AP13) | CFS!AP8:AP13 |
| CFS!AP16 | CFS\|16\|CFS!r3 | Y37 | same_period | Debt!AP14 | Debt!AP14 |
| CFS!AP17 | CFS\|17\|CFS!r3 | Y37 | same_period | Debt!AP10 | Debt!AP10 |
| CFS!AP19 | CFS\|19\|CFS!r3 | Y37 | same_period | AP14+AP16+AP17 | CFS!AP14, CFS!AP16, CFS!AP17 |
| CFS!AP21 | CFS\|21\|CFS!r3 | Y37 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AP25,0),MAX(AP19+AO25,0)) | Input Assumptions!D45, P&L!AP25, CFS!AP19, CFS!AO25 |
| CFS!AP23 | CFS\|23\|CFS!r3 | Y37 | same_period | AP19+AP21 | CFS!AP19, CFS!AP21 |
| CFS!AP25 | CFS\|25\|CFS!r3 | Y37 | rollforward | AO25+AP23 | CFS!AO25, CFS!AP23 |
| CFS!AP8 | CFS\|8\|CFS!r3 | Y37 | same_period | Operation!AO14 | Operation!AO14 |
| CFS!AQ10 | CFS\|10\|CFS!r3 | Y38 | same_period | -Operation!AP21 | Operation!AP21 |
| CFS!AQ12 | CFS\|12\|CFS!r3 | Y38 | same_period | 'P&L'!AQ23 | P&L!AQ23 |
| CFS!AQ14 | CFS\|14\|CFS!r3 | Y38 | aggregation | SUM(AQ8:AQ13) | CFS!AQ8:AQ13 |
| CFS!AQ16 | CFS\|16\|CFS!r3 | Y38 | same_period | Debt!AQ14 | Debt!AQ14 |
| CFS!AQ17 | CFS\|17\|CFS!r3 | Y38 | same_period | Debt!AQ10 | Debt!AQ10 |
| CFS!AQ19 | CFS\|19\|CFS!r3 | Y38 | same_period | AQ14+AQ16+AQ17 | CFS!AQ14, CFS!AQ16, CFS!AQ17 |
| CFS!AQ21 | CFS\|21\|CFS!r3 | Y38 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AQ25,0),MAX(AQ19+AP25,0)) | Input Assumptions!D45, P&L!AQ25, CFS!AQ19, CFS!AP25 |
| CFS!AQ23 | CFS\|23\|CFS!r3 | Y38 | same_period | AQ19+AQ21 | CFS!AQ19, CFS!AQ21 |
| CFS!AQ25 | CFS\|25\|CFS!r3 | Y38 | rollforward | AP25+AQ23 | CFS!AP25, CFS!AQ23 |
| CFS!AQ8 | CFS\|8\|CFS!r3 | Y38 | same_period | Operation!AP14 | Operation!AP14 |
| CFS!AR10 | CFS\|10\|CFS!r3 | Y39 | same_period | -Operation!AQ21 | Operation!AQ21 |
| CFS!AR12 | CFS\|12\|CFS!r3 | Y39 | same_period | 'P&L'!AR23 | P&L!AR23 |
| CFS!AR14 | CFS\|14\|CFS!r3 | Y39 | aggregation | SUM(AR8:AR13) | CFS!AR8:AR13 |
| CFS!AR16 | CFS\|16\|CFS!r3 | Y39 | same_period | Debt!AR14 | Debt!AR14 |
| CFS!AR17 | CFS\|17\|CFS!r3 | Y39 | same_period | Debt!AR10 | Debt!AR10 |
| CFS!AR19 | CFS\|19\|CFS!r3 | Y39 | same_period | AR14+AR16+AR17 | CFS!AR14, CFS!AR16, CFS!AR17 |
| CFS!AR21 | CFS\|21\|CFS!r3 | Y39 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AR25,0),MAX(AR19+AQ25,0)) | Input Assumptions!D45, P&L!AR25, CFS!AR19, CFS!AQ25 |
| CFS!AR23 | CFS\|23\|CFS!r3 | Y39 | same_period | AR19+AR21 | CFS!AR19, CFS!AR21 |
| CFS!AR25 | CFS\|25\|CFS!r3 | Y39 | rollforward | AQ25+AR23 | CFS!AQ25, CFS!AR23 |
| CFS!AR8 | CFS\|8\|CFS!r3 | Y39 | same_period | Operation!AQ14 | Operation!AQ14 |
| CFS!AS10 | CFS\|10\|CFS!r3 | Y40 | same_period | -Operation!AR21 | Operation!AR21 |
| CFS!AS12 | CFS\|12\|CFS!r3 | Y40 | same_period | 'P&L'!AS23 | P&L!AS23 |
| CFS!AS14 | CFS\|14\|CFS!r3 | Y40 | aggregation | SUM(AS8:AS13) | CFS!AS8:AS13 |
| CFS!AS16 | CFS\|16\|CFS!r3 | Y40 | same_period | Debt!AS14 | Debt!AS14 |
| CFS!AS17 | CFS\|17\|CFS!r3 | Y40 | same_period | Debt!AS10 | Debt!AS10 |
| CFS!AS19 | CFS\|19\|CFS!r3 | Y40 | same_period | AS14+AS16+AS17 | CFS!AS14, CFS!AS16, CFS!AS17 |
| CFS!AS21 | CFS\|21\|CFS!r3 | Y40 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!AS25,0),MAX(AS19+AR25,0)) | Input Assumptions!D45, P&L!AS25, CFS!AS19, CFS!AR25 |
| CFS!AS23 | CFS\|23\|CFS!r3 | Y40 | same_period | AS19+AS21 | CFS!AS19, CFS!AS21 |
| CFS!AS25 | CFS\|25\|CFS!r3 | Y40 | rollforward | AR25+AS23 | CFS!AR25, CFS!AS23 |
| CFS!AS8 | CFS\|8\|CFS!r3 | Y40 | same_period | Operation!AR14 | Operation!AR14 |
| CFS!F10 | CFS\|10\|CFS!r3 | Y1 | same_period | -Operation!E21 | Operation!E21 |
| CFS!F12 | CFS\|12\|CFS!r3 | Y1 | same_period | 'P&L'!F23 | P&L!F23 |
| CFS!F14 | CFS\|14\|CFS!r3 | Y1 | aggregation | SUM(F8:F13) | CFS!F8:F13 |
| CFS!F16 | CFS\|16\|CFS!r3 | Y1 | same_period | Debt!F14 | Debt!F14 |
| CFS!F17 | CFS\|17\|CFS!r3 | Y1 | same_period | Debt!F10 | Debt!F10 |
| CFS!F19 | CFS\|19\|CFS!r3 | Y1 | same_period | F14+F16+F17 | CFS!F14, CFS!F16, CFS!F17 |
| CFS!F21 | CFS\|21\|CFS!r3 | Y1 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!F25,0),MAX(F19+E25,0)) | Input Assumptions!D45, P&L!F25, CFS!F19, CFS!E25 |
| CFS!F23 | CFS\|23\|CFS!r3 | Y1 | same_period | F19+F21 | CFS!F19, CFS!F21 |
| CFS!F25 | CFS\|25\|CFS!r3 | Y1 | same_period | E25+F23 | CFS!E25, CFS!F23 |
| CFS!F8 | CFS\|8\|CFS!r3 | Y1 | same_period | Operation!E14 | Operation!E14 |
| CFS!G10 | CFS\|10\|CFS!r3 | Y2 | same_period | -Operation!F21 | Operation!F21 |
| CFS!G12 | CFS\|12\|CFS!r3 | Y2 | same_period | 'P&L'!G23 | P&L!G23 |
| CFS!G14 | CFS\|14\|CFS!r3 | Y2 | aggregation | SUM(G8:G13) | CFS!G8:G13 |
| CFS!G16 | CFS\|16\|CFS!r3 | Y2 | same_period | Debt!G14 | Debt!G14 |
| CFS!G17 | CFS\|17\|CFS!r3 | Y2 | same_period | Debt!G10 | Debt!G10 |
| CFS!G19 | CFS\|19\|CFS!r3 | Y2 | same_period | G14+G16+G17 | CFS!G14, CFS!G16, CFS!G17 |
| CFS!G21 | CFS\|21\|CFS!r3 | Y2 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!G25,0),MAX(G19+F25,0)) | Input Assumptions!D45, P&L!G25, CFS!G19, CFS!F25 |
| CFS!G23 | CFS\|23\|CFS!r3 | Y2 | same_period | G19+G21 | CFS!G19, CFS!G21 |
| CFS!G25 | CFS\|25\|CFS!r3 | Y2 | rollforward | F25+G23 | CFS!F25, CFS!G23 |
| CFS!G8 | CFS\|8\|CFS!r3 | Y2 | same_period | Operation!F14 | Operation!F14 |
| CFS!H10 | CFS\|10\|CFS!r3 | Y3 | same_period | -Operation!G21 | Operation!G21 |
| CFS!H12 | CFS\|12\|CFS!r3 | Y3 | same_period | 'P&L'!H23 | P&L!H23 |
| CFS!H14 | CFS\|14\|CFS!r3 | Y3 | aggregation | SUM(H8:H13) | CFS!H8:H13 |
| CFS!H16 | CFS\|16\|CFS!r3 | Y3 | same_period | Debt!H14 | Debt!H14 |
| CFS!H17 | CFS\|17\|CFS!r3 | Y3 | same_period | Debt!H10 | Debt!H10 |
| CFS!H19 | CFS\|19\|CFS!r3 | Y3 | same_period | H14+H16+H17 | CFS!H14, CFS!H16, CFS!H17 |
| CFS!H21 | CFS\|21\|CFS!r3 | Y3 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!H25,0),MAX(H19+G25,0)) | Input Assumptions!D45, P&L!H25, CFS!H19, CFS!G25 |
| CFS!H23 | CFS\|23\|CFS!r3 | Y3 | same_period | H19+H21 | CFS!H19, CFS!H21 |
| CFS!H25 | CFS\|25\|CFS!r3 | Y3 | rollforward | G25+H23 | CFS!G25, CFS!H23 |
| CFS!H8 | CFS\|8\|CFS!r3 | Y3 | same_period | Operation!G14 | Operation!G14 |
| CFS!I10 | CFS\|10\|CFS!r3 | Y4 | same_period | -Operation!H21 | Operation!H21 |
| CFS!I12 | CFS\|12\|CFS!r3 | Y4 | same_period | 'P&L'!I23 | P&L!I23 |
| CFS!I14 | CFS\|14\|CFS!r3 | Y4 | aggregation | SUM(I8:I13) | CFS!I8:I13 |
| CFS!I16 | CFS\|16\|CFS!r3 | Y4 | same_period | Debt!I14 | Debt!I14 |
| CFS!I17 | CFS\|17\|CFS!r3 | Y4 | same_period | Debt!I10 | Debt!I10 |
| CFS!I19 | CFS\|19\|CFS!r3 | Y4 | same_period | I14+I16+I17 | CFS!I14, CFS!I16, CFS!I17 |
| CFS!I21 | CFS\|21\|CFS!r3 | Y4 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!I25,0),MAX(I19+H25,0)) | Input Assumptions!D45, P&L!I25, CFS!I19, CFS!H25 |
| CFS!I23 | CFS\|23\|CFS!r3 | Y4 | same_period | I19+I21 | CFS!I19, CFS!I21 |
| CFS!I25 | CFS\|25\|CFS!r3 | Y4 | rollforward | H25+I23 | CFS!H25, CFS!I23 |
| CFS!I8 | CFS\|8\|CFS!r3 | Y4 | same_period | Operation!H14 | Operation!H14 |
| CFS!J10 | CFS\|10\|CFS!r3 | Y5 | same_period | -Operation!I21 | Operation!I21 |
| CFS!J12 | CFS\|12\|CFS!r3 | Y5 | same_period | 'P&L'!J23 | P&L!J23 |
| CFS!J14 | CFS\|14\|CFS!r3 | Y5 | aggregation | SUM(J8:J13) | CFS!J8:J13 |
| CFS!J16 | CFS\|16\|CFS!r3 | Y5 | same_period | Debt!J14 | Debt!J14 |
| CFS!J17 | CFS\|17\|CFS!r3 | Y5 | same_period | Debt!J10 | Debt!J10 |
| CFS!J19 | CFS\|19\|CFS!r3 | Y5 | same_period | J14+J16+J17 | CFS!J14, CFS!J16, CFS!J17 |
| CFS!J21 | CFS\|21\|CFS!r3 | Y5 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!J25,0),MAX(J19+I25,0)) | Input Assumptions!D45, P&L!J25, CFS!J19, CFS!I25 |
| CFS!J23 | CFS\|23\|CFS!r3 | Y5 | same_period | J19+J21 | CFS!J19, CFS!J21 |
| CFS!J25 | CFS\|25\|CFS!r3 | Y5 | rollforward | I25+J23 | CFS!I25, CFS!J23 |
| CFS!J8 | CFS\|8\|CFS!r3 | Y5 | same_period | Operation!I14 | Operation!I14 |
| CFS!K10 | CFS\|10\|CFS!r3 | Y6 | same_period | -Operation!J21 | Operation!J21 |
| CFS!K12 | CFS\|12\|CFS!r3 | Y6 | same_period | 'P&L'!K23 | P&L!K23 |
| CFS!K14 | CFS\|14\|CFS!r3 | Y6 | aggregation | SUM(K8:K13) | CFS!K8:K13 |
| CFS!K16 | CFS\|16\|CFS!r3 | Y6 | same_period | Debt!K14 | Debt!K14 |
| CFS!K17 | CFS\|17\|CFS!r3 | Y6 | same_period | Debt!K10 | Debt!K10 |
| CFS!K19 | CFS\|19\|CFS!r3 | Y6 | same_period | K14+K16+K17 | CFS!K14, CFS!K16, CFS!K17 |
| CFS!K21 | CFS\|21\|CFS!r3 | Y6 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!K25,0),MAX(K19+J25,0)) | Input Assumptions!D45, P&L!K25, CFS!K19, CFS!J25 |
| CFS!K23 | CFS\|23\|CFS!r3 | Y6 | same_period | K19+K21 | CFS!K19, CFS!K21 |
| CFS!K25 | CFS\|25\|CFS!r3 | Y6 | rollforward | J25+K23 | CFS!J25, CFS!K23 |
| CFS!K8 | CFS\|8\|CFS!r3 | Y6 | same_period | Operation!J14 | Operation!J14 |
| CFS!L10 | CFS\|10\|CFS!r3 | Y7 | same_period | -Operation!K21 | Operation!K21 |
| CFS!L12 | CFS\|12\|CFS!r3 | Y7 | same_period | 'P&L'!L23 | P&L!L23 |
| CFS!L14 | CFS\|14\|CFS!r3 | Y7 | aggregation | SUM(L8:L13) | CFS!L8:L13 |
| CFS!L16 | CFS\|16\|CFS!r3 | Y7 | same_period | Debt!L14 | Debt!L14 |
| CFS!L17 | CFS\|17\|CFS!r3 | Y7 | same_period | Debt!L10 | Debt!L10 |
| CFS!L19 | CFS\|19\|CFS!r3 | Y7 | same_period | L14+L16+L17 | CFS!L14, CFS!L16, CFS!L17 |
| CFS!L21 | CFS\|21\|CFS!r3 | Y7 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!L25,0),MAX(L19+K25,0)) | Input Assumptions!D45, P&L!L25, CFS!L19, CFS!K25 |
| CFS!L23 | CFS\|23\|CFS!r3 | Y7 | same_period | L19+L21 | CFS!L19, CFS!L21 |
| CFS!L25 | CFS\|25\|CFS!r3 | Y7 | rollforward | K25+L23 | CFS!K25, CFS!L23 |
| CFS!L8 | CFS\|8\|CFS!r3 | Y7 | same_period | Operation!K14 | Operation!K14 |
| CFS!M10 | CFS\|10\|CFS!r3 | Y8 | same_period | -Operation!L21 | Operation!L21 |
| CFS!M12 | CFS\|12\|CFS!r3 | Y8 | same_period | 'P&L'!M23 | P&L!M23 |
| CFS!M14 | CFS\|14\|CFS!r3 | Y8 | aggregation | SUM(M8:M13) | CFS!M8:M13 |
| CFS!M16 | CFS\|16\|CFS!r3 | Y8 | same_period | Debt!M14 | Debt!M14 |
| CFS!M17 | CFS\|17\|CFS!r3 | Y8 | same_period | Debt!M10 | Debt!M10 |
| CFS!M19 | CFS\|19\|CFS!r3 | Y8 | same_period | M14+M16+M17 | CFS!M14, CFS!M16, CFS!M17 |
| CFS!M21 | CFS\|21\|CFS!r3 | Y8 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!M25,0),MAX(M19+L25,0)) | Input Assumptions!D45, P&L!M25, CFS!M19, CFS!L25 |
| CFS!M23 | CFS\|23\|CFS!r3 | Y8 | same_period | M19+M21 | CFS!M19, CFS!M21 |
| CFS!M25 | CFS\|25\|CFS!r3 | Y8 | rollforward | L25+M23 | CFS!L25, CFS!M23 |
| CFS!M8 | CFS\|8\|CFS!r3 | Y8 | same_period | Operation!L14 | Operation!L14 |
| CFS!N10 | CFS\|10\|CFS!r3 | Y9 | same_period | -Operation!M21 | Operation!M21 |
| CFS!N12 | CFS\|12\|CFS!r3 | Y9 | same_period | 'P&L'!N23 | P&L!N23 |
| CFS!N14 | CFS\|14\|CFS!r3 | Y9 | aggregation | SUM(N8:N13) | CFS!N8:N13 |
| CFS!N16 | CFS\|16\|CFS!r3 | Y9 | same_period | Debt!N14 | Debt!N14 |
| CFS!N17 | CFS\|17\|CFS!r3 | Y9 | same_period | Debt!N10 | Debt!N10 |
| CFS!N19 | CFS\|19\|CFS!r3 | Y9 | same_period | N14+N16+N17 | CFS!N14, CFS!N16, CFS!N17 |
| CFS!N21 | CFS\|21\|CFS!r3 | Y9 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!N25,0),MAX(N19+M25,0)) | Input Assumptions!D45, P&L!N25, CFS!N19, CFS!M25 |
| CFS!N23 | CFS\|23\|CFS!r3 | Y9 | same_period | N19+N21 | CFS!N19, CFS!N21 |
| CFS!N25 | CFS\|25\|CFS!r3 | Y9 | rollforward | M25+N23 | CFS!M25, CFS!N23 |
| CFS!N8 | CFS\|8\|CFS!r3 | Y9 | same_period | Operation!M14 | Operation!M14 |
| CFS!O10 | CFS\|10\|CFS!r3 | Y10 | same_period | -Operation!N21 | Operation!N21 |
| CFS!O12 | CFS\|12\|CFS!r3 | Y10 | same_period | 'P&L'!O23 | P&L!O23 |
| CFS!O14 | CFS\|14\|CFS!r3 | Y10 | aggregation | SUM(O8:O13) | CFS!O8:O13 |
| CFS!O16 | CFS\|16\|CFS!r3 | Y10 | same_period | Debt!O14 | Debt!O14 |
| CFS!O17 | CFS\|17\|CFS!r3 | Y10 | same_period | Debt!O10 | Debt!O10 |
| CFS!O19 | CFS\|19\|CFS!r3 | Y10 | same_period | O14+O16+O17 | CFS!O14, CFS!O16, CFS!O17 |
| CFS!O21 | CFS\|21\|CFS!r3 | Y10 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!O25,0),MAX(O19+N25,0)) | Input Assumptions!D45, P&L!O25, CFS!O19, CFS!N25 |
| CFS!O23 | CFS\|23\|CFS!r3 | Y10 | same_period | O19+O21 | CFS!O19, CFS!O21 |
| CFS!O25 | CFS\|25\|CFS!r3 | Y10 | rollforward | N25+O23 | CFS!N25, CFS!O23 |
| CFS!O8 | CFS\|8\|CFS!r3 | Y10 | same_period | Operation!N14 | Operation!N14 |
| CFS!P10 | CFS\|10\|CFS!r3 | Y11 | same_period | -Operation!O21 | Operation!O21 |
| CFS!P12 | CFS\|12\|CFS!r3 | Y11 | same_period | 'P&L'!P23 | P&L!P23 |
| CFS!P14 | CFS\|14\|CFS!r3 | Y11 | aggregation | SUM(P8:P13) | CFS!P8:P13 |
| CFS!P16 | CFS\|16\|CFS!r3 | Y11 | same_period | Debt!P14 | Debt!P14 |
| CFS!P17 | CFS\|17\|CFS!r3 | Y11 | same_period | Debt!P10 | Debt!P10 |
| CFS!P19 | CFS\|19\|CFS!r3 | Y11 | same_period | P14+P16+P17 | CFS!P14, CFS!P16, CFS!P17 |
| CFS!P21 | CFS\|21\|CFS!r3 | Y11 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!P25,0),MAX(P19+O25,0)) | Input Assumptions!D45, P&L!P25, CFS!P19, CFS!O25 |
| CFS!P23 | CFS\|23\|CFS!r3 | Y11 | same_period | P19+P21 | CFS!P19, CFS!P21 |
| CFS!P25 | CFS\|25\|CFS!r3 | Y11 | rollforward | O25+P23 | CFS!O25, CFS!P23 |
| CFS!P8 | CFS\|8\|CFS!r3 | Y11 | same_period | Operation!O14 | Operation!O14 |
| CFS!Q10 | CFS\|10\|CFS!r3 | Y12 | same_period | -Operation!P21 | Operation!P21 |
| CFS!Q12 | CFS\|12\|CFS!r3 | Y12 | same_period | 'P&L'!Q23 | P&L!Q23 |
| CFS!Q14 | CFS\|14\|CFS!r3 | Y12 | aggregation | SUM(Q8:Q13) | CFS!Q8:Q13 |
| CFS!Q16 | CFS\|16\|CFS!r3 | Y12 | same_period | Debt!Q14 | Debt!Q14 |
| CFS!Q17 | CFS\|17\|CFS!r3 | Y12 | same_period | Debt!Q10 | Debt!Q10 |
| CFS!Q19 | CFS\|19\|CFS!r3 | Y12 | same_period | Q14+Q16+Q17 | CFS!Q14, CFS!Q16, CFS!Q17 |
| CFS!Q21 | CFS\|21\|CFS!r3 | Y12 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!Q25,0),MAX(Q19+P25,0)) | Input Assumptions!D45, P&L!Q25, CFS!Q19, CFS!P25 |
| CFS!Q23 | CFS\|23\|CFS!r3 | Y12 | same_period | Q19+Q21 | CFS!Q19, CFS!Q21 |
| CFS!Q25 | CFS\|25\|CFS!r3 | Y12 | rollforward | P25+Q23 | CFS!P25, CFS!Q23 |
| CFS!Q8 | CFS\|8\|CFS!r3 | Y12 | same_period | Operation!P14 | Operation!P14 |
| CFS!R10 | CFS\|10\|CFS!r3 | Y13 | same_period | -Operation!Q21 | Operation!Q21 |
| CFS!R12 | CFS\|12\|CFS!r3 | Y13 | same_period | 'P&L'!R23 | P&L!R23 |
| CFS!R14 | CFS\|14\|CFS!r3 | Y13 | aggregation | SUM(R8:R13) | CFS!R8:R13 |
| CFS!R16 | CFS\|16\|CFS!r3 | Y13 | same_period | Debt!R14 | Debt!R14 |
| CFS!R17 | CFS\|17\|CFS!r3 | Y13 | same_period | Debt!R10 | Debt!R10 |
| CFS!R19 | CFS\|19\|CFS!r3 | Y13 | same_period | R14+R16+R17 | CFS!R14, CFS!R16, CFS!R17 |
| CFS!R21 | CFS\|21\|CFS!r3 | Y13 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!R25,0),MAX(R19+Q25,0)) | Input Assumptions!D45, P&L!R25, CFS!R19, CFS!Q25 |
| CFS!R23 | CFS\|23\|CFS!r3 | Y13 | same_period | R19+R21 | CFS!R19, CFS!R21 |
| CFS!R25 | CFS\|25\|CFS!r3 | Y13 | rollforward | Q25+R23 | CFS!Q25, CFS!R23 |
| CFS!R8 | CFS\|8\|CFS!r3 | Y13 | same_period | Operation!Q14 | Operation!Q14 |
| CFS!S10 | CFS\|10\|CFS!r3 | Y14 | same_period | -Operation!R21 | Operation!R21 |
| CFS!S12 | CFS\|12\|CFS!r3 | Y14 | same_period | 'P&L'!S23 | P&L!S23 |
| CFS!S14 | CFS\|14\|CFS!r3 | Y14 | aggregation | SUM(S8:S13) | CFS!S8:S13 |
| CFS!S16 | CFS\|16\|CFS!r3 | Y14 | same_period | Debt!S14 | Debt!S14 |
| CFS!S17 | CFS\|17\|CFS!r3 | Y14 | same_period | Debt!S10 | Debt!S10 |
| CFS!S19 | CFS\|19\|CFS!r3 | Y14 | same_period | S14+S16+S17 | CFS!S14, CFS!S16, CFS!S17 |
| CFS!S21 | CFS\|21\|CFS!r3 | Y14 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!S25,0),MAX(S19+R25,0)) | Input Assumptions!D45, P&L!S25, CFS!S19, CFS!R25 |
| CFS!S23 | CFS\|23\|CFS!r3 | Y14 | same_period | S19+S21 | CFS!S19, CFS!S21 |
| CFS!S25 | CFS\|25\|CFS!r3 | Y14 | rollforward | R25+S23 | CFS!R25, CFS!S23 |
| CFS!S8 | CFS\|8\|CFS!r3 | Y14 | same_period | Operation!R14 | Operation!R14 |
| CFS!T10 | CFS\|10\|CFS!r3 | Y15 | same_period | -Operation!S21 | Operation!S21 |
| CFS!T12 | CFS\|12\|CFS!r3 | Y15 | same_period | 'P&L'!T23 | P&L!T23 |
| CFS!T14 | CFS\|14\|CFS!r3 | Y15 | aggregation | SUM(T8:T13) | CFS!T8:T13 |
| CFS!T16 | CFS\|16\|CFS!r3 | Y15 | same_period | Debt!T14 | Debt!T14 |
| CFS!T17 | CFS\|17\|CFS!r3 | Y15 | same_period | Debt!T10 | Debt!T10 |
| CFS!T19 | CFS\|19\|CFS!r3 | Y15 | same_period | T14+T16+T17 | CFS!T14, CFS!T16, CFS!T17 |
| CFS!T21 | CFS\|21\|CFS!r3 | Y15 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!T25,0),MAX(T19+S25,0)) | Input Assumptions!D45, P&L!T25, CFS!T19, CFS!S25 |
| CFS!T23 | CFS\|23\|CFS!r3 | Y15 | same_period | T19+T21 | CFS!T19, CFS!T21 |
| CFS!T25 | CFS\|25\|CFS!r3 | Y15 | rollforward | S25+T23 | CFS!S25, CFS!T23 |
| CFS!T8 | CFS\|8\|CFS!r3 | Y15 | same_period | Operation!S14 | Operation!S14 |
| CFS!U10 | CFS\|10\|CFS!r3 | Y16 | same_period | -Operation!T21 | Operation!T21 |
| CFS!U12 | CFS\|12\|CFS!r3 | Y16 | same_period | 'P&L'!U23 | P&L!U23 |
| CFS!U14 | CFS\|14\|CFS!r3 | Y16 | aggregation | SUM(U8:U13) | CFS!U8:U13 |
| CFS!U16 | CFS\|16\|CFS!r3 | Y16 | same_period | Debt!U14 | Debt!U14 |
| CFS!U17 | CFS\|17\|CFS!r3 | Y16 | same_period | Debt!U10 | Debt!U10 |
| CFS!U19 | CFS\|19\|CFS!r3 | Y16 | same_period | U14+U16+U17 | CFS!U14, CFS!U16, CFS!U17 |
| CFS!U21 | CFS\|21\|CFS!r3 | Y16 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!U25,0),MAX(U19+T25,0)) | Input Assumptions!D45, P&L!U25, CFS!U19, CFS!T25 |
| CFS!U23 | CFS\|23\|CFS!r3 | Y16 | same_period | U19+U21 | CFS!U19, CFS!U21 |
| CFS!U25 | CFS\|25\|CFS!r3 | Y16 | rollforward | T25+U23 | CFS!T25, CFS!U23 |
| CFS!U8 | CFS\|8\|CFS!r3 | Y16 | same_period | Operation!T14 | Operation!T14 |
| CFS!V10 | CFS\|10\|CFS!r3 | Y17 | same_period | -Operation!U21 | Operation!U21 |
| CFS!V12 | CFS\|12\|CFS!r3 | Y17 | same_period | 'P&L'!V23 | P&L!V23 |
| CFS!V14 | CFS\|14\|CFS!r3 | Y17 | aggregation | SUM(V8:V13) | CFS!V8:V13 |
| CFS!V16 | CFS\|16\|CFS!r3 | Y17 | same_period | Debt!V14 | Debt!V14 |
| CFS!V17 | CFS\|17\|CFS!r3 | Y17 | same_period | Debt!V10 | Debt!V10 |
| CFS!V19 | CFS\|19\|CFS!r3 | Y17 | same_period | V14+V16+V17 | CFS!V14, CFS!V16, CFS!V17 |
| CFS!V21 | CFS\|21\|CFS!r3 | Y17 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!V25,0),MAX(V19+U25,0)) | Input Assumptions!D45, P&L!V25, CFS!V19, CFS!U25 |
| CFS!V23 | CFS\|23\|CFS!r3 | Y17 | same_period | V19+V21 | CFS!V19, CFS!V21 |
| CFS!V25 | CFS\|25\|CFS!r3 | Y17 | rollforward | U25+V23 | CFS!U25, CFS!V23 |
| CFS!V8 | CFS\|8\|CFS!r3 | Y17 | same_period | Operation!U14 | Operation!U14 |
| CFS!W10 | CFS\|10\|CFS!r3 | Y18 | same_period | -Operation!V21 | Operation!V21 |
| CFS!W12 | CFS\|12\|CFS!r3 | Y18 | same_period | 'P&L'!W23 | P&L!W23 |
| CFS!W14 | CFS\|14\|CFS!r3 | Y18 | aggregation | SUM(W8:W13) | CFS!W8:W13 |
| CFS!W16 | CFS\|16\|CFS!r3 | Y18 | same_period | Debt!W14 | Debt!W14 |
| CFS!W17 | CFS\|17\|CFS!r3 | Y18 | same_period | Debt!W10 | Debt!W10 |
| CFS!W19 | CFS\|19\|CFS!r3 | Y18 | same_period | W14+W16+W17 | CFS!W14, CFS!W16, CFS!W17 |
| CFS!W21 | CFS\|21\|CFS!r3 | Y18 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!W25,0),MAX(W19+V25,0)) | Input Assumptions!D45, P&L!W25, CFS!W19, CFS!V25 |
| CFS!W23 | CFS\|23\|CFS!r3 | Y18 | same_period | W19+W21 | CFS!W19, CFS!W21 |
| CFS!W25 | CFS\|25\|CFS!r3 | Y18 | rollforward | V25+W23 | CFS!V25, CFS!W23 |
| CFS!W8 | CFS\|8\|CFS!r3 | Y18 | same_period | Operation!V14 | Operation!V14 |
| CFS!X10 | CFS\|10\|CFS!r3 | Y19 | same_period | -Operation!W21 | Operation!W21 |
| CFS!X12 | CFS\|12\|CFS!r3 | Y19 | same_period | 'P&L'!X23 | P&L!X23 |
| CFS!X14 | CFS\|14\|CFS!r3 | Y19 | aggregation | SUM(X8:X13) | CFS!X8:X13 |
| CFS!X16 | CFS\|16\|CFS!r3 | Y19 | same_period | Debt!X14 | Debt!X14 |
| CFS!X17 | CFS\|17\|CFS!r3 | Y19 | same_period | Debt!X10 | Debt!X10 |
| CFS!X19 | CFS\|19\|CFS!r3 | Y19 | same_period | X14+X16+X17 | CFS!X14, CFS!X16, CFS!X17 |
| CFS!X21 | CFS\|21\|CFS!r3 | Y19 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!X25,0),MAX(X19+W25,0)) | Input Assumptions!D45, P&L!X25, CFS!X19, CFS!W25 |
| CFS!X23 | CFS\|23\|CFS!r3 | Y19 | same_period | X19+X21 | CFS!X19, CFS!X21 |
| CFS!X25 | CFS\|25\|CFS!r3 | Y19 | rollforward | W25+X23 | CFS!W25, CFS!X23 |
| CFS!X8 | CFS\|8\|CFS!r3 | Y19 | same_period | Operation!W14 | Operation!W14 |
| CFS!Y10 | CFS\|10\|CFS!r3 | Y20 | same_period | -Operation!X21 | Operation!X21 |
| CFS!Y12 | CFS\|12\|CFS!r3 | Y20 | same_period | 'P&L'!Y23 | P&L!Y23 |
| CFS!Y14 | CFS\|14\|CFS!r3 | Y20 | aggregation | SUM(Y8:Y13) | CFS!Y8:Y13 |
| CFS!Y16 | CFS\|16\|CFS!r3 | Y20 | same_period | Debt!Y14 | Debt!Y14 |
| CFS!Y17 | CFS\|17\|CFS!r3 | Y20 | same_period | Debt!Y10 | Debt!Y10 |
| CFS!Y19 | CFS\|19\|CFS!r3 | Y20 | same_period | Y14+Y16+Y17 | CFS!Y14, CFS!Y16, CFS!Y17 |
| CFS!Y21 | CFS\|21\|CFS!r3 | Y20 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!Y25,0),MAX(Y19+X25,0)) | Input Assumptions!D45, P&L!Y25, CFS!Y19, CFS!X25 |
| CFS!Y23 | CFS\|23\|CFS!r3 | Y20 | same_period | Y19+Y21 | CFS!Y19, CFS!Y21 |
| CFS!Y25 | CFS\|25\|CFS!r3 | Y20 | rollforward | X25+Y23 | CFS!X25, CFS!Y23 |
| CFS!Y8 | CFS\|8\|CFS!r3 | Y20 | same_period | Operation!X14 | Operation!X14 |
| CFS!Z10 | CFS\|10\|CFS!r3 | Y21 | same_period | -Operation!Y21 | Operation!Y21 |
| CFS!Z12 | CFS\|12\|CFS!r3 | Y21 | same_period | 'P&L'!Z23 | P&L!Z23 |
| CFS!Z14 | CFS\|14\|CFS!r3 | Y21 | aggregation | SUM(Z8:Z13) | CFS!Z8:Z13 |
| CFS!Z16 | CFS\|16\|CFS!r3 | Y21 | same_period | Debt!Z14 | Debt!Z14 |
| CFS!Z17 | CFS\|17\|CFS!r3 | Y21 | same_period | Debt!Z10 | Debt!Z10 |
| CFS!Z19 | CFS\|19\|CFS!r3 | Y21 | same_period | Z14+Z16+Z17 | CFS!Z14, CFS!Z16, CFS!Z17 |
| CFS!Z21 | CFS\|21\|CFS!r3 | Y21 | aggregation | -MIN(MAX('Input Assumptions'!$D$45*'P&L'!Z25,0),MAX(Z19+Y25,0)) | Input Assumptions!D45, P&L!Z25, CFS!Z19, CFS!Y25 |
| CFS!Z23 | CFS\|23\|CFS!r3 | Y21 | same_period | Z19+Z21 | CFS!Z19, CFS!Z21 |
| CFS!Z25 | CFS\|25\|CFS!r3 | Y21 | rollforward | Y25+Z23 | CFS!Y25, CFS!Z23 |
| CFS!Z8 | CFS\|8\|CFS!r3 | Y21 | same_period | Operation!Y14 | Operation!Y14 |
| Construction!AA12 | Construction\|12\|Construction!r2 | Y23 | same_period | AA8 | Construction!AA8 |
| Construction!AA13 | Construction\|13\|Construction!r2 | Y23 | same_period | AA37 | Construction!AA37 |
| Construction!AA14 | Construction\|14\|Construction!r2 | Y23 | same_period | AA38 | Construction!AA38 |
| Construction!AA15 | Construction\|15\|Construction!r2 | Y23 | same_period | AA39 | Construction!AA39 |
| Construction!AA16 | Construction\|16\|Construction!r2 | Y23 | aggregation | SUM(AA12:AA15) | Construction!AA12:AA15 |
| Construction!AA26 | Construction\|26\|Construction!r2 | Y23 | conditional | IF(MAX($C$22-SUM($D$26:Z26),0)>AA19,AA19,MAX($C$22-SUM($D$26:Z26),0)) | Construction!C22, Construction!D26:Z26, Construction!AA19 |
| Construction!AA27 | Construction\|27\|Construction!r2 | Y23 | conditional | IF(AA19-AA26>0,AA19-AA26,0) | Construction!AA19, Construction!AA26 |
| Construction!AA28 | Construction\|28\|Construction!r2 | Y23 | aggregation | SUM(AA26:AA27) | Construction!AA26:AA27 |
| Construction!AA33 | Construction\|33\|Construction!r2 | Y23 | rollforward | Z35 | Construction!Z35 |
| Construction!AA34 | Construction\|34\|Construction!r2 | Y23 | same_period | AA27 | Construction!AA27 |
| Construction!AA35 | Construction\|35\|Construction!r2 | Y23 | aggregation | SUM(AA33:AA34) | Construction!AA33:AA34 |
| Construction!AA37 | Construction\|37\|Construction!r2 | Y23 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!Z13 | Input Assumptions!D37, Construction!C34, TBA!Z13 |
| Construction!AA38 | Construction\|38\|Construction!r2 | Y23 | same_period | ($C$34-AA33)*TBA!Z14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AA33, TBA!Z14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AA39 | Construction\|39\|Construction!r2 | Y23 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AA33*TBA!Z14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AA33, TBA!Z14 |
| Construction!AA43 | Construction\|43\|Construction!r2 | Y23 | same_period | AA16-AA28<0.01 | Construction!AA16, Construction!AA28 |
| Construction!AA6 | Construction\|6\|Construction!r2 | Y23 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!Z8 | Input Assumptions!D25, Input Assumptions!D9, TBA!Z8 |
| Construction!AA8 | Construction\|8\|Construction!r2 | Y23 | aggregation | SUM(AA6:AA7) | Construction!AA6:AA7 |
| Construction!AB12 | Construction\|12\|Construction!r2 | Y24 | same_period | AB8 | Construction!AB8 |
| Construction!AB13 | Construction\|13\|Construction!r2 | Y24 | same_period | AB37 | Construction!AB37 |
| Construction!AB14 | Construction\|14\|Construction!r2 | Y24 | same_period | AB38 | Construction!AB38 |
| Construction!AB15 | Construction\|15\|Construction!r2 | Y24 | same_period | AB39 | Construction!AB39 |
| Construction!AB16 | Construction\|16\|Construction!r2 | Y24 | aggregation | SUM(AB12:AB15) | Construction!AB12:AB15 |
| Construction!AB26 | Construction\|26\|Construction!r2 | Y24 | conditional | IF(MAX($C$22-SUM($D$26:AA26),0)>AB19,AB19,MAX($C$22-SUM($D$26:AA26),0)) | Construction!C22, Construction!D26:AA26, Construction!AB19 |
| Construction!AB27 | Construction\|27\|Construction!r2 | Y24 | conditional | IF(AB19-AB26>0,AB19-AB26,0) | Construction!AB19, Construction!AB26 |
| Construction!AB28 | Construction\|28\|Construction!r2 | Y24 | aggregation | SUM(AB26:AB27) | Construction!AB26:AB27 |
| Construction!AB33 | Construction\|33\|Construction!r2 | Y24 | rollforward | AA35 | Construction!AA35 |
| Construction!AB34 | Construction\|34\|Construction!r2 | Y24 | same_period | AB27 | Construction!AB27 |
| Construction!AB35 | Construction\|35\|Construction!r2 | Y24 | aggregation | SUM(AB33:AB34) | Construction!AB33:AB34 |
| Construction!AB37 | Construction\|37\|Construction!r2 | Y24 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AA13 | Input Assumptions!D37, Construction!C34, TBA!AA13 |
| Construction!AB38 | Construction\|38\|Construction!r2 | Y24 | same_period | ($C$34-AB33)*TBA!AA14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AB33, TBA!AA14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AB39 | Construction\|39\|Construction!r2 | Y24 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AB33*TBA!AA14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AB33, TBA!AA14 |
| Construction!AB43 | Construction\|43\|Construction!r2 | Y24 | same_period | AB16-AB28<0.01 | Construction!AB16, Construction!AB28 |
| Construction!AB6 | Construction\|6\|Construction!r2 | Y24 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AA8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AA8 |
| Construction!AB8 | Construction\|8\|Construction!r2 | Y24 | aggregation | SUM(AB6:AB7) | Construction!AB6:AB7 |
| Construction!AC12 | Construction\|12\|Construction!r2 | Y25 | same_period | AC8 | Construction!AC8 |
| Construction!AC13 | Construction\|13\|Construction!r2 | Y25 | same_period | AC37 | Construction!AC37 |
| Construction!AC14 | Construction\|14\|Construction!r2 | Y25 | same_period | AC38 | Construction!AC38 |
| Construction!AC15 | Construction\|15\|Construction!r2 | Y25 | same_period | AC39 | Construction!AC39 |
| Construction!AC16 | Construction\|16\|Construction!r2 | Y25 | aggregation | SUM(AC12:AC15) | Construction!AC12:AC15 |
| Construction!AC26 | Construction\|26\|Construction!r2 | Y25 | conditional | IF(MAX($C$22-SUM($D$26:AB26),0)>AC19,AC19,MAX($C$22-SUM($D$26:AB26),0)) | Construction!C22, Construction!D26:AB26, Construction!AC19 |
| Construction!AC27 | Construction\|27\|Construction!r2 | Y25 | conditional | IF(AC19-AC26>0,AC19-AC26,0) | Construction!AC19, Construction!AC26 |
| Construction!AC28 | Construction\|28\|Construction!r2 | Y25 | aggregation | SUM(AC26:AC27) | Construction!AC26:AC27 |
| Construction!AC33 | Construction\|33\|Construction!r2 | Y25 | rollforward | AB35 | Construction!AB35 |
| Construction!AC34 | Construction\|34\|Construction!r2 | Y25 | same_period | AC27 | Construction!AC27 |
| Construction!AC35 | Construction\|35\|Construction!r2 | Y25 | aggregation | SUM(AC33:AC34) | Construction!AC33:AC34 |
| Construction!AC37 | Construction\|37\|Construction!r2 | Y25 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AB13 | Input Assumptions!D37, Construction!C34, TBA!AB13 |
| Construction!AC38 | Construction\|38\|Construction!r2 | Y25 | same_period | ($C$34-AC33)*TBA!AB14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AC33, TBA!AB14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AC39 | Construction\|39\|Construction!r2 | Y25 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AC33*TBA!AB14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AC33, TBA!AB14 |
| Construction!AC43 | Construction\|43\|Construction!r2 | Y25 | same_period | AC16-AC28<0.01 | Construction!AC16, Construction!AC28 |
| Construction!AC6 | Construction\|6\|Construction!r2 | Y25 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AB8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AB8 |
| Construction!AC8 | Construction\|8\|Construction!r2 | Y25 | aggregation | SUM(AC6:AC7) | Construction!AC6:AC7 |
| Construction!AD12 | Construction\|12\|Construction!r2 | Y26 | same_period | AD8 | Construction!AD8 |
| Construction!AD13 | Construction\|13\|Construction!r2 | Y26 | same_period | AD37 | Construction!AD37 |
| Construction!AD14 | Construction\|14\|Construction!r2 | Y26 | same_period | AD38 | Construction!AD38 |
| Construction!AD15 | Construction\|15\|Construction!r2 | Y26 | same_period | AD39 | Construction!AD39 |
| Construction!AD16 | Construction\|16\|Construction!r2 | Y26 | aggregation | SUM(AD12:AD15) | Construction!AD12:AD15 |
| Construction!AD26 | Construction\|26\|Construction!r2 | Y26 | conditional | IF(MAX($C$22-SUM($D$26:AC26),0)>AD19,AD19,MAX($C$22-SUM($D$26:AC26),0)) | Construction!C22, Construction!D26:AC26, Construction!AD19 |
| Construction!AD27 | Construction\|27\|Construction!r2 | Y26 | conditional | IF(AD19-AD26>0,AD19-AD26,0) | Construction!AD19, Construction!AD26 |
| Construction!AD28 | Construction\|28\|Construction!r2 | Y26 | aggregation | SUM(AD26:AD27) | Construction!AD26:AD27 |
| Construction!AD33 | Construction\|33\|Construction!r2 | Y26 | rollforward | AC35 | Construction!AC35 |
| Construction!AD34 | Construction\|34\|Construction!r2 | Y26 | same_period | AD27 | Construction!AD27 |
| Construction!AD35 | Construction\|35\|Construction!r2 | Y26 | aggregation | SUM(AD33:AD34) | Construction!AD33:AD34 |
| Construction!AD37 | Construction\|37\|Construction!r2 | Y26 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AC13 | Input Assumptions!D37, Construction!C34, TBA!AC13 |
| Construction!AD38 | Construction\|38\|Construction!r2 | Y26 | same_period | ($C$34-AD33)*TBA!AC14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AD33, TBA!AC14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AD39 | Construction\|39\|Construction!r2 | Y26 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AD33*TBA!AC14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AD33, TBA!AC14 |
| Construction!AD43 | Construction\|43\|Construction!r2 | Y26 | same_period | AD16-AD28<0.01 | Construction!AD16, Construction!AD28 |
| Construction!AD6 | Construction\|6\|Construction!r2 | Y26 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AC8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AC8 |
| Construction!AD8 | Construction\|8\|Construction!r2 | Y26 | aggregation | SUM(AD6:AD7) | Construction!AD6:AD7 |
| Construction!AE12 | Construction\|12\|Construction!r2 | Y27 | same_period | AE8 | Construction!AE8 |
| Construction!AE13 | Construction\|13\|Construction!r2 | Y27 | same_period | AE37 | Construction!AE37 |
| Construction!AE14 | Construction\|14\|Construction!r2 | Y27 | same_period | AE38 | Construction!AE38 |
| Construction!AE15 | Construction\|15\|Construction!r2 | Y27 | same_period | AE39 | Construction!AE39 |
| Construction!AE16 | Construction\|16\|Construction!r2 | Y27 | aggregation | SUM(AE12:AE15) | Construction!AE12:AE15 |
| Construction!AE26 | Construction\|26\|Construction!r2 | Y27 | conditional | IF(MAX($C$22-SUM($D$26:AD26),0)>AE19,AE19,MAX($C$22-SUM($D$26:AD26),0)) | Construction!C22, Construction!D26:AD26, Construction!AE19 |
| Construction!AE27 | Construction\|27\|Construction!r2 | Y27 | conditional | IF(AE19-AE26>0,AE19-AE26,0) | Construction!AE19, Construction!AE26 |
| Construction!AE28 | Construction\|28\|Construction!r2 | Y27 | aggregation | SUM(AE26:AE27) | Construction!AE26:AE27 |
| Construction!AE33 | Construction\|33\|Construction!r2 | Y27 | rollforward | AD35 | Construction!AD35 |
| Construction!AE34 | Construction\|34\|Construction!r2 | Y27 | same_period | AE27 | Construction!AE27 |
| Construction!AE35 | Construction\|35\|Construction!r2 | Y27 | aggregation | SUM(AE33:AE34) | Construction!AE33:AE34 |
| Construction!AE37 | Construction\|37\|Construction!r2 | Y27 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AD13 | Input Assumptions!D37, Construction!C34, TBA!AD13 |
| Construction!AE38 | Construction\|38\|Construction!r2 | Y27 | same_period | ($C$34-AE33)*TBA!AD14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AE33, TBA!AD14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AE39 | Construction\|39\|Construction!r2 | Y27 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AE33*TBA!AD14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AE33, TBA!AD14 |
| Construction!AE43 | Construction\|43\|Construction!r2 | Y27 | same_period | AE16-AE28<0.01 | Construction!AE16, Construction!AE28 |
| Construction!AE6 | Construction\|6\|Construction!r2 | Y27 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AD8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AD8 |
| Construction!AE8 | Construction\|8\|Construction!r2 | Y27 | aggregation | SUM(AE6:AE7) | Construction!AE6:AE7 |
| Construction!AF12 | Construction\|12\|Construction!r2 | Y28 | same_period | AF8 | Construction!AF8 |
| Construction!AF13 | Construction\|13\|Construction!r2 | Y28 | same_period | AF37 | Construction!AF37 |
| Construction!AF14 | Construction\|14\|Construction!r2 | Y28 | same_period | AF38 | Construction!AF38 |
| Construction!AF15 | Construction\|15\|Construction!r2 | Y28 | same_period | AF39 | Construction!AF39 |
| Construction!AF16 | Construction\|16\|Construction!r2 | Y28 | aggregation | SUM(AF12:AF15) | Construction!AF12:AF15 |
| Construction!AF26 | Construction\|26\|Construction!r2 | Y28 | conditional | IF(MAX($C$22-SUM($D$26:AE26),0)>AF19,AF19,MAX($C$22-SUM($D$26:AE26),0)) | Construction!C22, Construction!D26:AE26, Construction!AF19 |
| Construction!AF27 | Construction\|27\|Construction!r2 | Y28 | conditional | IF(AF19-AF26>0,AF19-AF26,0) | Construction!AF19, Construction!AF26 |
| Construction!AF28 | Construction\|28\|Construction!r2 | Y28 | aggregation | SUM(AF26:AF27) | Construction!AF26:AF27 |
| Construction!AF33 | Construction\|33\|Construction!r2 | Y28 | rollforward | AE35 | Construction!AE35 |
| Construction!AF34 | Construction\|34\|Construction!r2 | Y28 | same_period | AF27 | Construction!AF27 |
| Construction!AF35 | Construction\|35\|Construction!r2 | Y28 | aggregation | SUM(AF33:AF34) | Construction!AF33:AF34 |
| Construction!AF37 | Construction\|37\|Construction!r2 | Y28 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AE13 | Input Assumptions!D37, Construction!C34, TBA!AE13 |
| Construction!AF38 | Construction\|38\|Construction!r2 | Y28 | same_period | ($C$34-AF33)*TBA!AE14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AF33, TBA!AE14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AF39 | Construction\|39\|Construction!r2 | Y28 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AF33*TBA!AE14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AF33, TBA!AE14 |
| Construction!AF43 | Construction\|43\|Construction!r2 | Y28 | same_period | AF16-AF28<0.01 | Construction!AF16, Construction!AF28 |
| Construction!AF6 | Construction\|6\|Construction!r2 | Y28 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AE8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AE8 |
| Construction!AF8 | Construction\|8\|Construction!r2 | Y28 | aggregation | SUM(AF6:AF7) | Construction!AF6:AF7 |
| Construction!AG12 | Construction\|12\|Construction!r2 | Y29 | same_period | AG8 | Construction!AG8 |
| Construction!AG13 | Construction\|13\|Construction!r2 | Y29 | same_period | AG37 | Construction!AG37 |
| Construction!AG14 | Construction\|14\|Construction!r2 | Y29 | same_period | AG38 | Construction!AG38 |
| Construction!AG15 | Construction\|15\|Construction!r2 | Y29 | same_period | AG39 | Construction!AG39 |
| Construction!AG16 | Construction\|16\|Construction!r2 | Y29 | aggregation | SUM(AG12:AG15) | Construction!AG12:AG15 |
| Construction!AG26 | Construction\|26\|Construction!r2 | Y29 | conditional | IF(MAX($C$22-SUM($D$26:AF26),0)>AG19,AG19,MAX($C$22-SUM($D$26:AF26),0)) | Construction!C22, Construction!D26:AF26, Construction!AG19 |
| Construction!AG27 | Construction\|27\|Construction!r2 | Y29 | conditional | IF(AG19-AG26>0,AG19-AG26,0) | Construction!AG19, Construction!AG26 |
| Construction!AG28 | Construction\|28\|Construction!r2 | Y29 | aggregation | SUM(AG26:AG27) | Construction!AG26:AG27 |
| Construction!AG33 | Construction\|33\|Construction!r2 | Y29 | rollforward | AF35 | Construction!AF35 |
| Construction!AG34 | Construction\|34\|Construction!r2 | Y29 | same_period | AG27 | Construction!AG27 |
| Construction!AG35 | Construction\|35\|Construction!r2 | Y29 | aggregation | SUM(AG33:AG34) | Construction!AG33:AG34 |
| Construction!AG37 | Construction\|37\|Construction!r2 | Y29 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AF13 | Input Assumptions!D37, Construction!C34, TBA!AF13 |
| Construction!AG38 | Construction\|38\|Construction!r2 | Y29 | same_period | ($C$34-AG33)*TBA!AF14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AG33, TBA!AF14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AG39 | Construction\|39\|Construction!r2 | Y29 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AG33*TBA!AF14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AG33, TBA!AF14 |
| Construction!AG43 | Construction\|43\|Construction!r2 | Y29 | same_period | AG16-AG28<0.01 | Construction!AG16, Construction!AG28 |
| Construction!AG6 | Construction\|6\|Construction!r2 | Y29 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AF8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AF8 |
| Construction!AG8 | Construction\|8\|Construction!r2 | Y29 | aggregation | SUM(AG6:AG7) | Construction!AG6:AG7 |
| Construction!AH12 | Construction\|12\|Construction!r2 | Y30 | same_period | AH8 | Construction!AH8 |
| Construction!AH13 | Construction\|13\|Construction!r2 | Y30 | same_period | AH37 | Construction!AH37 |
| Construction!AH14 | Construction\|14\|Construction!r2 | Y30 | same_period | AH38 | Construction!AH38 |
| Construction!AH15 | Construction\|15\|Construction!r2 | Y30 | same_period | AH39 | Construction!AH39 |
| Construction!AH16 | Construction\|16\|Construction!r2 | Y30 | aggregation | SUM(AH12:AH15) | Construction!AH12:AH15 |
| Construction!AH26 | Construction\|26\|Construction!r2 | Y30 | conditional | IF(MAX($C$22-SUM($D$26:AG26),0)>AH19,AH19,MAX($C$22-SUM($D$26:AG26),0)) | Construction!C22, Construction!D26:AG26, Construction!AH19 |
| Construction!AH27 | Construction\|27\|Construction!r2 | Y30 | conditional | IF(AH19-AH26>0,AH19-AH26,0) | Construction!AH19, Construction!AH26 |
| Construction!AH28 | Construction\|28\|Construction!r2 | Y30 | aggregation | SUM(AH26:AH27) | Construction!AH26:AH27 |
| Construction!AH33 | Construction\|33\|Construction!r2 | Y30 | rollforward | AG35 | Construction!AG35 |
| Construction!AH34 | Construction\|34\|Construction!r2 | Y30 | same_period | AH27 | Construction!AH27 |
| Construction!AH35 | Construction\|35\|Construction!r2 | Y30 | aggregation | SUM(AH33:AH34) | Construction!AH33:AH34 |
| Construction!AH37 | Construction\|37\|Construction!r2 | Y30 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AG13 | Input Assumptions!D37, Construction!C34, TBA!AG13 |
| Construction!AH38 | Construction\|38\|Construction!r2 | Y30 | same_period | ($C$34-AH33)*TBA!AG14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AH33, TBA!AG14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AH39 | Construction\|39\|Construction!r2 | Y30 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AH33*TBA!AG14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AH33, TBA!AG14 |
| Construction!AH43 | Construction\|43\|Construction!r2 | Y30 | same_period | AH16-AH28<0.01 | Construction!AH16, Construction!AH28 |
| Construction!AH6 | Construction\|6\|Construction!r2 | Y30 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AG8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AG8 |
| Construction!AH8 | Construction\|8\|Construction!r2 | Y30 | aggregation | SUM(AH6:AH7) | Construction!AH6:AH7 |
| Construction!AI12 | Construction\|12\|Construction!r2 | Y31 | same_period | AI8 | Construction!AI8 |
| Construction!AI13 | Construction\|13\|Construction!r2 | Y31 | same_period | AI37 | Construction!AI37 |
| Construction!AI14 | Construction\|14\|Construction!r2 | Y31 | same_period | AI38 | Construction!AI38 |
| Construction!AI15 | Construction\|15\|Construction!r2 | Y31 | same_period | AI39 | Construction!AI39 |
| Construction!AI16 | Construction\|16\|Construction!r2 | Y31 | aggregation | SUM(AI12:AI15) | Construction!AI12:AI15 |
| Construction!AI26 | Construction\|26\|Construction!r2 | Y31 | conditional | IF(MAX($C$22-SUM($D$26:AH26),0)>AI19,AI19,MAX($C$22-SUM($D$26:AH26),0)) | Construction!C22, Construction!D26:AH26, Construction!AI19 |
| Construction!AI27 | Construction\|27\|Construction!r2 | Y31 | conditional | IF(AI19-AI26>0,AI19-AI26,0) | Construction!AI19, Construction!AI26 |
| Construction!AI28 | Construction\|28\|Construction!r2 | Y31 | aggregation | SUM(AI26:AI27) | Construction!AI26:AI27 |
| Construction!AI33 | Construction\|33\|Construction!r2 | Y31 | rollforward | AH35 | Construction!AH35 |
| Construction!AI34 | Construction\|34\|Construction!r2 | Y31 | same_period | AI27 | Construction!AI27 |
| Construction!AI35 | Construction\|35\|Construction!r2 | Y31 | aggregation | SUM(AI33:AI34) | Construction!AI33:AI34 |
| Construction!AI37 | Construction\|37\|Construction!r2 | Y31 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AH13 | Input Assumptions!D37, Construction!C34, TBA!AH13 |
| Construction!AI38 | Construction\|38\|Construction!r2 | Y31 | same_period | ($C$34-AI33)*TBA!AH14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AI33, TBA!AH14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AI39 | Construction\|39\|Construction!r2 | Y31 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AI33*TBA!AH14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AI33, TBA!AH14 |
| Construction!AI43 | Construction\|43\|Construction!r2 | Y31 | same_period | AI16-AI28<0.01 | Construction!AI16, Construction!AI28 |
| Construction!AI6 | Construction\|6\|Construction!r2 | Y31 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AH8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AH8 |
| Construction!AI8 | Construction\|8\|Construction!r2 | Y31 | aggregation | SUM(AI6:AI7) | Construction!AI6:AI7 |
| Construction!AJ12 | Construction\|12\|Construction!r2 | Y32 | same_period | AJ8 | Construction!AJ8 |
| Construction!AJ13 | Construction\|13\|Construction!r2 | Y32 | same_period | AJ37 | Construction!AJ37 |
| Construction!AJ14 | Construction\|14\|Construction!r2 | Y32 | same_period | AJ38 | Construction!AJ38 |
| Construction!AJ15 | Construction\|15\|Construction!r2 | Y32 | same_period | AJ39 | Construction!AJ39 |
| Construction!AJ16 | Construction\|16\|Construction!r2 | Y32 | aggregation | SUM(AJ12:AJ15) | Construction!AJ12:AJ15 |
| Construction!AJ26 | Construction\|26\|Construction!r2 | Y32 | conditional | IF(MAX($C$22-SUM($D$26:AI26),0)>AJ19,AJ19,MAX($C$22-SUM($D$26:AI26),0)) | Construction!C22, Construction!D26:AI26, Construction!AJ19 |
| Construction!AJ27 | Construction\|27\|Construction!r2 | Y32 | conditional | IF(AJ19-AJ26>0,AJ19-AJ26,0) | Construction!AJ19, Construction!AJ26 |
| Construction!AJ28 | Construction\|28\|Construction!r2 | Y32 | aggregation | SUM(AJ26:AJ27) | Construction!AJ26:AJ27 |
| Construction!AJ33 | Construction\|33\|Construction!r2 | Y32 | rollforward | AI35 | Construction!AI35 |
| Construction!AJ34 | Construction\|34\|Construction!r2 | Y32 | same_period | AJ27 | Construction!AJ27 |
| Construction!AJ35 | Construction\|35\|Construction!r2 | Y32 | aggregation | SUM(AJ33:AJ34) | Construction!AJ33:AJ34 |
| Construction!AJ37 | Construction\|37\|Construction!r2 | Y32 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AI13 | Input Assumptions!D37, Construction!C34, TBA!AI13 |
| Construction!AJ38 | Construction\|38\|Construction!r2 | Y32 | same_period | ($C$34-AJ33)*TBA!AI14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AJ33, TBA!AI14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AJ39 | Construction\|39\|Construction!r2 | Y32 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AJ33*TBA!AI14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AJ33, TBA!AI14 |
| Construction!AJ43 | Construction\|43\|Construction!r2 | Y32 | same_period | AJ16-AJ28<0.01 | Construction!AJ16, Construction!AJ28 |
| Construction!AJ6 | Construction\|6\|Construction!r2 | Y32 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AI8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AI8 |
| Construction!AJ8 | Construction\|8\|Construction!r2 | Y32 | aggregation | SUM(AJ6:AJ7) | Construction!AJ6:AJ7 |
| Construction!AK12 | Construction\|12\|Construction!r2 | Y33 | same_period | AK8 | Construction!AK8 |
| Construction!AK13 | Construction\|13\|Construction!r2 | Y33 | same_period | AK37 | Construction!AK37 |
| Construction!AK14 | Construction\|14\|Construction!r2 | Y33 | same_period | AK38 | Construction!AK38 |
| Construction!AK15 | Construction\|15\|Construction!r2 | Y33 | same_period | AK39 | Construction!AK39 |
| Construction!AK16 | Construction\|16\|Construction!r2 | Y33 | aggregation | SUM(AK12:AK15) | Construction!AK12:AK15 |
| Construction!AK26 | Construction\|26\|Construction!r2 | Y33 | conditional | IF(MAX($C$22-SUM($D$26:AJ26),0)>AK19,AK19,MAX($C$22-SUM($D$26:AJ26),0)) | Construction!C22, Construction!D26:AJ26, Construction!AK19 |
| Construction!AK27 | Construction\|27\|Construction!r2 | Y33 | conditional | IF(AK19-AK26>0,AK19-AK26,0) | Construction!AK19, Construction!AK26 |
| Construction!AK28 | Construction\|28\|Construction!r2 | Y33 | aggregation | SUM(AK26:AK27) | Construction!AK26:AK27 |
| Construction!AK33 | Construction\|33\|Construction!r2 | Y33 | rollforward | AJ35 | Construction!AJ35 |
| Construction!AK34 | Construction\|34\|Construction!r2 | Y33 | same_period | AK27 | Construction!AK27 |
| Construction!AK35 | Construction\|35\|Construction!r2 | Y33 | aggregation | SUM(AK33:AK34) | Construction!AK33:AK34 |
| Construction!AK37 | Construction\|37\|Construction!r2 | Y33 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AJ13 | Input Assumptions!D37, Construction!C34, TBA!AJ13 |
| Construction!AK38 | Construction\|38\|Construction!r2 | Y33 | same_period | ($C$34-AK33)*TBA!AJ14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AK33, TBA!AJ14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AK39 | Construction\|39\|Construction!r2 | Y33 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AK33*TBA!AJ14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AK33, TBA!AJ14 |
| Construction!AK43 | Construction\|43\|Construction!r2 | Y33 | same_period | AK16-AK28<0.01 | Construction!AK16, Construction!AK28 |
| Construction!AK6 | Construction\|6\|Construction!r2 | Y33 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AJ8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AJ8 |
| Construction!AK8 | Construction\|8\|Construction!r2 | Y33 | aggregation | SUM(AK6:AK7) | Construction!AK6:AK7 |
| Construction!AL12 | Construction\|12\|Construction!r2 | Y34 | same_period | AL8 | Construction!AL8 |
| Construction!AL13 | Construction\|13\|Construction!r2 | Y34 | same_period | AL37 | Construction!AL37 |
| Construction!AL14 | Construction\|14\|Construction!r2 | Y34 | same_period | AL38 | Construction!AL38 |
| Construction!AL15 | Construction\|15\|Construction!r2 | Y34 | same_period | AL39 | Construction!AL39 |
| Construction!AL16 | Construction\|16\|Construction!r2 | Y34 | aggregation | SUM(AL12:AL15) | Construction!AL12:AL15 |
| Construction!AL26 | Construction\|26\|Construction!r2 | Y34 | conditional | IF(MAX($C$22-SUM($D$26:AK26),0)>AL19,AL19,MAX($C$22-SUM($D$26:AK26),0)) | Construction!C22, Construction!D26:AK26, Construction!AL19 |
| Construction!AL27 | Construction\|27\|Construction!r2 | Y34 | conditional | IF(AL19-AL26>0,AL19-AL26,0) | Construction!AL19, Construction!AL26 |
| Construction!AL28 | Construction\|28\|Construction!r2 | Y34 | aggregation | SUM(AL26:AL27) | Construction!AL26:AL27 |
| Construction!AL33 | Construction\|33\|Construction!r2 | Y34 | rollforward | AK35 | Construction!AK35 |
| Construction!AL34 | Construction\|34\|Construction!r2 | Y34 | same_period | AL27 | Construction!AL27 |
| Construction!AL35 | Construction\|35\|Construction!r2 | Y34 | aggregation | SUM(AL33:AL34) | Construction!AL33:AL34 |
| Construction!AL37 | Construction\|37\|Construction!r2 | Y34 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AK13 | Input Assumptions!D37, Construction!C34, TBA!AK13 |
| Construction!AL38 | Construction\|38\|Construction!r2 | Y34 | same_period | ($C$34-AL33)*TBA!AK14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AL33, TBA!AK14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AL39 | Construction\|39\|Construction!r2 | Y34 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AL33*TBA!AK14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AL33, TBA!AK14 |
| Construction!AL43 | Construction\|43\|Construction!r2 | Y34 | same_period | AL16-AL28<0.01 | Construction!AL16, Construction!AL28 |
| Construction!AL6 | Construction\|6\|Construction!r2 | Y34 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AK8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AK8 |
| Construction!AL8 | Construction\|8\|Construction!r2 | Y34 | aggregation | SUM(AL6:AL7) | Construction!AL6:AL7 |
| Construction!AM12 | Construction\|12\|Construction!r2 | Y35 | same_period | AM8 | Construction!AM8 |
| Construction!AM13 | Construction\|13\|Construction!r2 | Y35 | same_period | AM37 | Construction!AM37 |
| Construction!AM14 | Construction\|14\|Construction!r2 | Y35 | same_period | AM38 | Construction!AM38 |
| Construction!AM15 | Construction\|15\|Construction!r2 | Y35 | same_period | AM39 | Construction!AM39 |
| Construction!AM16 | Construction\|16\|Construction!r2 | Y35 | aggregation | SUM(AM12:AM15) | Construction!AM12:AM15 |
| Construction!AM26 | Construction\|26\|Construction!r2 | Y35 | conditional | IF(MAX($C$22-SUM($D$26:AL26),0)>AM19,AM19,MAX($C$22-SUM($D$26:AL26),0)) | Construction!C22, Construction!D26:AL26, Construction!AM19 |
| Construction!AM27 | Construction\|27\|Construction!r2 | Y35 | conditional | IF(AM19-AM26>0,AM19-AM26,0) | Construction!AM19, Construction!AM26 |
| Construction!AM28 | Construction\|28\|Construction!r2 | Y35 | aggregation | SUM(AM26:AM27) | Construction!AM26:AM27 |
| Construction!AM33 | Construction\|33\|Construction!r2 | Y35 | rollforward | AL35 | Construction!AL35 |
| Construction!AM34 | Construction\|34\|Construction!r2 | Y35 | same_period | AM27 | Construction!AM27 |
| Construction!AM35 | Construction\|35\|Construction!r2 | Y35 | aggregation | SUM(AM33:AM34) | Construction!AM33:AM34 |
| Construction!AM37 | Construction\|37\|Construction!r2 | Y35 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AL13 | Input Assumptions!D37, Construction!C34, TBA!AL13 |
| Construction!AM38 | Construction\|38\|Construction!r2 | Y35 | same_period | ($C$34-AM33)*TBA!AL14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AM33, TBA!AL14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AM39 | Construction\|39\|Construction!r2 | Y35 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AM33*TBA!AL14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AM33, TBA!AL14 |
| Construction!AM43 | Construction\|43\|Construction!r2 | Y35 | same_period | AM16-AM28<0.01 | Construction!AM16, Construction!AM28 |
| Construction!AM6 | Construction\|6\|Construction!r2 | Y35 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AL8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AL8 |
| Construction!AM8 | Construction\|8\|Construction!r2 | Y35 | aggregation | SUM(AM6:AM7) | Construction!AM6:AM7 |
| Construction!AN12 | Construction\|12\|Construction!r2 | Y36 | same_period | AN8 | Construction!AN8 |
| Construction!AN13 | Construction\|13\|Construction!r2 | Y36 | same_period | AN37 | Construction!AN37 |
| Construction!AN14 | Construction\|14\|Construction!r2 | Y36 | same_period | AN38 | Construction!AN38 |
| Construction!AN15 | Construction\|15\|Construction!r2 | Y36 | same_period | AN39 | Construction!AN39 |
| Construction!AN16 | Construction\|16\|Construction!r2 | Y36 | aggregation | SUM(AN12:AN15) | Construction!AN12:AN15 |
| Construction!AN26 | Construction\|26\|Construction!r2 | Y36 | conditional | IF(MAX($C$22-SUM($D$26:AM26),0)>AN19,AN19,MAX($C$22-SUM($D$26:AM26),0)) | Construction!C22, Construction!D26:AM26, Construction!AN19 |
| Construction!AN27 | Construction\|27\|Construction!r2 | Y36 | conditional | IF(AN19-AN26>0,AN19-AN26,0) | Construction!AN19, Construction!AN26 |
| Construction!AN28 | Construction\|28\|Construction!r2 | Y36 | aggregation | SUM(AN26:AN27) | Construction!AN26:AN27 |
| Construction!AN33 | Construction\|33\|Construction!r2 | Y36 | rollforward | AM35 | Construction!AM35 |
| Construction!AN34 | Construction\|34\|Construction!r2 | Y36 | same_period | AN27 | Construction!AN27 |
| Construction!AN35 | Construction\|35\|Construction!r2 | Y36 | aggregation | SUM(AN33:AN34) | Construction!AN33:AN34 |
| Construction!AN37 | Construction\|37\|Construction!r2 | Y36 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AM13 | Input Assumptions!D37, Construction!C34, TBA!AM13 |
| Construction!AN38 | Construction\|38\|Construction!r2 | Y36 | same_period | ($C$34-AN33)*TBA!AM14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AN33, TBA!AM14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AN39 | Construction\|39\|Construction!r2 | Y36 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AN33*TBA!AM14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AN33, TBA!AM14 |
| Construction!AN43 | Construction\|43\|Construction!r2 | Y36 | same_period | AN16-AN28<0.01 | Construction!AN16, Construction!AN28 |
| Construction!AN6 | Construction\|6\|Construction!r2 | Y36 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AM8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AM8 |
| Construction!AN8 | Construction\|8\|Construction!r2 | Y36 | aggregation | SUM(AN6:AN7) | Construction!AN6:AN7 |
| Construction!AO12 | Construction\|12\|Construction!r2 | Y37 | same_period | AO8 | Construction!AO8 |
| Construction!AO13 | Construction\|13\|Construction!r2 | Y37 | same_period | AO37 | Construction!AO37 |
| Construction!AO14 | Construction\|14\|Construction!r2 | Y37 | same_period | AO38 | Construction!AO38 |
| Construction!AO15 | Construction\|15\|Construction!r2 | Y37 | same_period | AO39 | Construction!AO39 |
| Construction!AO16 | Construction\|16\|Construction!r2 | Y37 | aggregation | SUM(AO12:AO15) | Construction!AO12:AO15 |
| Construction!AO26 | Construction\|26\|Construction!r2 | Y37 | conditional | IF(MAX($C$22-SUM($D$26:AN26),0)>AO19,AO19,MAX($C$22-SUM($D$26:AN26),0)) | Construction!C22, Construction!D26:AN26, Construction!AO19 |
| Construction!AO27 | Construction\|27\|Construction!r2 | Y37 | conditional | IF(AO19-AO26>0,AO19-AO26,0) | Construction!AO19, Construction!AO26 |
| Construction!AO28 | Construction\|28\|Construction!r2 | Y37 | aggregation | SUM(AO26:AO27) | Construction!AO26:AO27 |
| Construction!AO33 | Construction\|33\|Construction!r2 | Y37 | rollforward | AN35 | Construction!AN35 |
| Construction!AO34 | Construction\|34\|Construction!r2 | Y37 | same_period | AO27 | Construction!AO27 |
| Construction!AO35 | Construction\|35\|Construction!r2 | Y37 | aggregation | SUM(AO33:AO34) | Construction!AO33:AO34 |
| Construction!AO37 | Construction\|37\|Construction!r2 | Y37 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AN13 | Input Assumptions!D37, Construction!C34, TBA!AN13 |
| Construction!AO38 | Construction\|38\|Construction!r2 | Y37 | same_period | ($C$34-AO33)*TBA!AN14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AO33, TBA!AN14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AO39 | Construction\|39\|Construction!r2 | Y37 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AO33*TBA!AN14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AO33, TBA!AN14 |
| Construction!AO43 | Construction\|43\|Construction!r2 | Y37 | same_period | AO16-AO28<0.01 | Construction!AO16, Construction!AO28 |
| Construction!AO6 | Construction\|6\|Construction!r2 | Y37 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AN8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AN8 |
| Construction!AO8 | Construction\|8\|Construction!r2 | Y37 | aggregation | SUM(AO6:AO7) | Construction!AO6:AO7 |
| Construction!AP12 | Construction\|12\|Construction!r2 | Y38 | same_period | AP8 | Construction!AP8 |
| Construction!AP13 | Construction\|13\|Construction!r2 | Y38 | same_period | AP37 | Construction!AP37 |
| Construction!AP14 | Construction\|14\|Construction!r2 | Y38 | same_period | AP38 | Construction!AP38 |
| Construction!AP15 | Construction\|15\|Construction!r2 | Y38 | same_period | AP39 | Construction!AP39 |
| Construction!AP16 | Construction\|16\|Construction!r2 | Y38 | aggregation | SUM(AP12:AP15) | Construction!AP12:AP15 |
| Construction!AP26 | Construction\|26\|Construction!r2 | Y38 | conditional | IF(MAX($C$22-SUM($D$26:AO26),0)>AP19,AP19,MAX($C$22-SUM($D$26:AO26),0)) | Construction!C22, Construction!D26:AO26, Construction!AP19 |
| Construction!AP27 | Construction\|27\|Construction!r2 | Y38 | conditional | IF(AP19-AP26>0,AP19-AP26,0) | Construction!AP19, Construction!AP26 |
| Construction!AP28 | Construction\|28\|Construction!r2 | Y38 | aggregation | SUM(AP26:AP27) | Construction!AP26:AP27 |
| Construction!AP33 | Construction\|33\|Construction!r2 | Y38 | rollforward | AO35 | Construction!AO35 |
| Construction!AP34 | Construction\|34\|Construction!r2 | Y38 | same_period | AP27 | Construction!AP27 |
| Construction!AP35 | Construction\|35\|Construction!r2 | Y38 | aggregation | SUM(AP33:AP34) | Construction!AP33:AP34 |
| Construction!AP37 | Construction\|37\|Construction!r2 | Y38 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AO13 | Input Assumptions!D37, Construction!C34, TBA!AO13 |
| Construction!AP38 | Construction\|38\|Construction!r2 | Y38 | same_period | ($C$34-AP33)*TBA!AO14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AP33, TBA!AO14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AP39 | Construction\|39\|Construction!r2 | Y38 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AP33*TBA!AO14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AP33, TBA!AO14 |
| Construction!AP43 | Construction\|43\|Construction!r2 | Y38 | same_period | AP16-AP28<0.01 | Construction!AP16, Construction!AP28 |
| Construction!AP6 | Construction\|6\|Construction!r2 | Y38 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AO8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AO8 |
| Construction!AP8 | Construction\|8\|Construction!r2 | Y38 | aggregation | SUM(AP6:AP7) | Construction!AP6:AP7 |
| Construction!AQ12 | Construction\|12\|Construction!r2 | Y39 | same_period | AQ8 | Construction!AQ8 |
| Construction!AQ13 | Construction\|13\|Construction!r2 | Y39 | same_period | AQ37 | Construction!AQ37 |
| Construction!AQ14 | Construction\|14\|Construction!r2 | Y39 | same_period | AQ38 | Construction!AQ38 |
| Construction!AQ15 | Construction\|15\|Construction!r2 | Y39 | same_period | AQ39 | Construction!AQ39 |
| Construction!AQ16 | Construction\|16\|Construction!r2 | Y39 | aggregation | SUM(AQ12:AQ15) | Construction!AQ12:AQ15 |
| Construction!AQ26 | Construction\|26\|Construction!r2 | Y39 | conditional | IF(MAX($C$22-SUM($D$26:AP26),0)>AQ19,AQ19,MAX($C$22-SUM($D$26:AP26),0)) | Construction!C22, Construction!D26:AP26, Construction!AQ19 |
| Construction!AQ27 | Construction\|27\|Construction!r2 | Y39 | conditional | IF(AQ19-AQ26>0,AQ19-AQ26,0) | Construction!AQ19, Construction!AQ26 |
| Construction!AQ28 | Construction\|28\|Construction!r2 | Y39 | aggregation | SUM(AQ26:AQ27) | Construction!AQ26:AQ27 |
| Construction!AQ33 | Construction\|33\|Construction!r2 | Y39 | rollforward | AP35 | Construction!AP35 |
| Construction!AQ34 | Construction\|34\|Construction!r2 | Y39 | same_period | AQ27 | Construction!AQ27 |
| Construction!AQ35 | Construction\|35\|Construction!r2 | Y39 | aggregation | SUM(AQ33:AQ34) | Construction!AQ33:AQ34 |
| Construction!AQ37 | Construction\|37\|Construction!r2 | Y39 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AP13 | Input Assumptions!D37, Construction!C34, TBA!AP13 |
| Construction!AQ38 | Construction\|38\|Construction!r2 | Y39 | same_period | ($C$34-AQ33)*TBA!AP14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AQ33, TBA!AP14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AQ39 | Construction\|39\|Construction!r2 | Y39 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AQ33*TBA!AP14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AQ33, TBA!AP14 |
| Construction!AQ43 | Construction\|43\|Construction!r2 | Y39 | same_period | AQ16-AQ28<0.01 | Construction!AQ16, Construction!AQ28 |
| Construction!AQ6 | Construction\|6\|Construction!r2 | Y39 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AP8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AP8 |
| Construction!AQ8 | Construction\|8\|Construction!r2 | Y39 | aggregation | SUM(AQ6:AQ7) | Construction!AQ6:AQ7 |
| Construction!AR12 | Construction\|12\|Construction!r2 | Y40 | same_period | AR8 | Construction!AR8 |
| Construction!AR13 | Construction\|13\|Construction!r2 | Y40 | same_period | AR37 | Construction!AR37 |
| Construction!AR14 | Construction\|14\|Construction!r2 | Y40 | same_period | AR38 | Construction!AR38 |
| Construction!AR15 | Construction\|15\|Construction!r2 | Y40 | same_period | AR39 | Construction!AR39 |
| Construction!AR16 | Construction\|16\|Construction!r2 | Y40 | aggregation | SUM(AR12:AR15) | Construction!AR12:AR15 |
| Construction!AR26 | Construction\|26\|Construction!r2 | Y40 | conditional | IF(MAX($C$22-SUM($D$26:AQ26),0)>AR19,AR19,MAX($C$22-SUM($D$26:AQ26),0)) | Construction!C22, Construction!D26:AQ26, Construction!AR19 |
| Construction!AR27 | Construction\|27\|Construction!r2 | Y40 | conditional | IF(AR19-AR26>0,AR19-AR26,0) | Construction!AR19, Construction!AR26 |
| Construction!AR28 | Construction\|28\|Construction!r2 | Y40 | aggregation | SUM(AR26:AR27) | Construction!AR26:AR27 |
| Construction!AR33 | Construction\|33\|Construction!r2 | Y40 | rollforward | AQ35 | Construction!AQ35 |
| Construction!AR34 | Construction\|34\|Construction!r2 | Y40 | same_period | AR27 | Construction!AR27 |
| Construction!AR35 | Construction\|35\|Construction!r2 | Y40 | aggregation | SUM(AR33:AR34) | Construction!AR33:AR34 |
| Construction!AR37 | Construction\|37\|Construction!r2 | Y40 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!AQ13 | Input Assumptions!D37, Construction!C34, TBA!AQ13 |
| Construction!AR38 | Construction\|38\|Construction!r2 | Y40 | same_period | ($C$34-AR33)*TBA!AQ14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!AR33, TBA!AQ14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!AR39 | Construction\|39\|Construction!r2 | Y40 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*AR33*TBA!AQ14 | Input Assumptions!D35, Input Assumptions!D36, Construction!AR33, TBA!AQ14 |
| Construction!AR43 | Construction\|43\|Construction!r2 | Y40 | same_period | AR16-AR28<0.01 | Construction!AR16, Construction!AR28 |
| Construction!AR6 | Construction\|6\|Construction!r2 | Y40 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!AQ8 | Input Assumptions!D25, Input Assumptions!D9, TBA!AQ8 |
| Construction!AR8 | Construction\|8\|Construction!r2 | Y40 | aggregation | SUM(AR6:AR7) | Construction!AR6:AR7 |
| Construction!C12 | Construction\|12\|Construction!r2 |  | aggregation | SUM(E12:AR12) | Construction!E12:AR12 |
| Construction!C13 | Construction\|13\|Construction!r2 |  | aggregation | SUM(E13:AR13) | Construction!E13:AR13 |
| Construction!C14 | Construction\|14\|Construction!r2 |  | aggregation | SUM(E14:AR14) | Construction!E14:AR14 |
| Construction!C15 | Construction\|15\|Construction!r2 |  | aggregation | SUM(E15:AR15) | Construction!E15:AR15 |
| Construction!C16 | Construction\|16\|Construction!r2 |  | aggregation | SUM(E16:AR16) | Construction!E16:AR16 |
| Construction!C20 | Construction\|20\|Construction!r2 |  | aggregation | SUM(E19:AR19) | Construction!E19:AR19 |
| Construction!C21 | Construction\|21\|Construction!r2 |  | same_period | $C$20*'Input Assumptions'!$D$40 | Construction!C20, Input Assumptions!D40 |
| Construction!C22 | Construction\|22\|Construction!r2 |  | same_period | $C$20*(1-'Input Assumptions'!$D$40) | Construction!C20, Input Assumptions!D40 |
| Construction!C26 | Construction\|26\|Construction!r2 |  | aggregation | SUM(E26:AR26) | Construction!E26:AR26 |
| Construction!C27 | Construction\|27\|Construction!r2 |  | aggregation | SUM(E27:AR27) | Construction!E27:AR27 |
| Construction!C28 | Construction\|28\|Construction!r2 |  | aggregation | SUM(E28:AR28) | Construction!E28:AR28 |
| Construction!C34 | Construction\|34\|Construction!r2 |  | aggregation | SUM(E34:AR34) | Construction!E34:AR34 |
| Construction!C6 | Construction\|6\|Construction!r2 |  | aggregation | SUM(E6:AR6) | Construction!E6:AR6 |
| Construction!C8 | Construction\|8\|Construction!r2 |  | aggregation | SUM(E8:AR8) | Construction!E8:AR8 |
| Construction!E12 | Construction\|12\|Construction!r2 | Y1 | same_period | E8 | Construction!E8 |
| Construction!E13 | Construction\|13\|Construction!r2 | Y1 | same_period | E37 | Construction!E37 |
| Construction!E14 | Construction\|14\|Construction!r2 | Y1 | same_period | E38 | Construction!E38 |
| Construction!E15 | Construction\|15\|Construction!r2 | Y1 | same_period | E39 | Construction!E39 |
| Construction!E16 | Construction\|16\|Construction!r2 | Y1 | aggregation | SUM(E12:E15) | Construction!E12:E15 |
| Construction!E26 | Construction\|26\|Construction!r2 | Y1 | conditional | IF(MAX($C$22-SUM($D$26:D26),0)>E19,E19,MAX($C$22-SUM($D$26:D26),0)) | Construction!C22, Construction!D26:D26, Construction!E19 |
| Construction!E27 | Construction\|27\|Construction!r2 | Y1 | conditional | IF(E19-E26>0,E19-E26,0) | Construction!E19, Construction!E26 |
| Construction!E28 | Construction\|28\|Construction!r2 | Y1 | aggregation | SUM(E26:E27) | Construction!E26:E27 |
| Construction!E34 | Construction\|34\|Construction!r2 | Y1 | same_period | E27 | Construction!E27 |
| Construction!E35 | Construction\|35\|Construction!r2 | Y1 | aggregation | SUM(E33:E34) | Construction!E33:E34 |
| Construction!E37 | Construction\|37\|Construction!r2 | Y1 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!D13 | Input Assumptions!D37, Construction!C34, TBA!D13 |
| Construction!E38 | Construction\|38\|Construction!r2 | Y1 | same_period | ($C$34-E33)*TBA!D14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!E33, TBA!D14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!E39 | Construction\|39\|Construction!r2 | Y1 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*E33*TBA!D14 | Input Assumptions!D35, Input Assumptions!D36, Construction!E33, TBA!D14 |
| Construction!E43 | Construction\|43\|Construction!r2 | Y1 | same_period | E16-E28<0.01 | Construction!E16, Construction!E28 |
| Construction!E6 | Construction\|6\|Construction!r2 | Y1 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!D8 | Input Assumptions!D25, Input Assumptions!D9, TBA!D8 |
| Construction!E8 | Construction\|8\|Construction!r2 | Y1 | aggregation | SUM(E6:E7) | Construction!E6:E7 |
| Construction!F12 | Construction\|12\|Construction!r2 | Y2 | same_period | F8 | Construction!F8 |
| Construction!F13 | Construction\|13\|Construction!r2 | Y2 | same_period | F37 | Construction!F37 |
| Construction!F14 | Construction\|14\|Construction!r2 | Y2 | same_period | F38 | Construction!F38 |
| Construction!F15 | Construction\|15\|Construction!r2 | Y2 | same_period | F39 | Construction!F39 |
| Construction!F16 | Construction\|16\|Construction!r2 | Y2 | aggregation | SUM(F12:F15) | Construction!F12:F15 |
| Construction!F26 | Construction\|26\|Construction!r2 | Y2 | conditional | IF(MAX($C$22-SUM($D$26:E26),0)>F19,F19,MAX($C$22-SUM($D$26:E26),0)) | Construction!C22, Construction!D26:E26, Construction!F19 |
| Construction!F27 | Construction\|27\|Construction!r2 | Y2 | conditional | IF(F19-F26>0,F19-F26,0) | Construction!F19, Construction!F26 |
| Construction!F28 | Construction\|28\|Construction!r2 | Y2 | aggregation | SUM(F26:F27) | Construction!F26:F27 |
| Construction!F33 | Construction\|33\|Construction!r2 | Y2 | rollforward | E35 | Construction!E35 |
| Construction!F34 | Construction\|34\|Construction!r2 | Y2 | same_period | F27 | Construction!F27 |
| Construction!F35 | Construction\|35\|Construction!r2 | Y2 | aggregation | SUM(F33:F34) | Construction!F33:F34 |
| Construction!F37 | Construction\|37\|Construction!r2 | Y2 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!E13 | Input Assumptions!D37, Construction!C34, TBA!E13 |
| Construction!F38 | Construction\|38\|Construction!r2 | Y2 | same_period | ($C$34-F33)*TBA!E14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!F33, TBA!E14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!F39 | Construction\|39\|Construction!r2 | Y2 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*F33*TBA!E14 | Input Assumptions!D35, Input Assumptions!D36, Construction!F33, TBA!E14 |
| Construction!F43 | Construction\|43\|Construction!r2 | Y2 | same_period | F16-F28<0.01 | Construction!F16, Construction!F28 |
| Construction!F6 | Construction\|6\|Construction!r2 | Y2 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!E8 | Input Assumptions!D25, Input Assumptions!D9, TBA!E8 |
| Construction!F8 | Construction\|8\|Construction!r2 | Y2 | aggregation | SUM(F6:F7) | Construction!F6:F7 |
| Construction!G12 | Construction\|12\|Construction!r2 | Y3 | same_period | G8 | Construction!G8 |
| Construction!G13 | Construction\|13\|Construction!r2 | Y3 | same_period | G37 | Construction!G37 |
| Construction!G14 | Construction\|14\|Construction!r2 | Y3 | same_period | G38 | Construction!G38 |
| Construction!G15 | Construction\|15\|Construction!r2 | Y3 | same_period | G39 | Construction!G39 |
| Construction!G16 | Construction\|16\|Construction!r2 | Y3 | aggregation | SUM(G12:G15) | Construction!G12:G15 |
| Construction!G26 | Construction\|26\|Construction!r2 | Y3 | conditional | IF(MAX($C$22-SUM($D$26:F26),0)>G19,G19,MAX($C$22-SUM($D$26:F26),0)) | Construction!C22, Construction!D26:F26, Construction!G19 |
| Construction!G27 | Construction\|27\|Construction!r2 | Y3 | conditional | IF(G19-G26>0,G19-G26,0) | Construction!G19, Construction!G26 |
| Construction!G28 | Construction\|28\|Construction!r2 | Y3 | aggregation | SUM(G26:G27) | Construction!G26:G27 |
| Construction!G33 | Construction\|33\|Construction!r2 | Y3 | rollforward | F35 | Construction!F35 |
| Construction!G34 | Construction\|34\|Construction!r2 | Y3 | same_period | G27 | Construction!G27 |
| Construction!G35 | Construction\|35\|Construction!r2 | Y3 | aggregation | SUM(G33:G34) | Construction!G33:G34 |
| Construction!G37 | Construction\|37\|Construction!r2 | Y3 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!F13 | Input Assumptions!D37, Construction!C34, TBA!F13 |
| Construction!G38 | Construction\|38\|Construction!r2 | Y3 | same_period | ($C$34-G33)*TBA!F14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!G33, TBA!F14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!G39 | Construction\|39\|Construction!r2 | Y3 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*G33*TBA!F14 | Input Assumptions!D35, Input Assumptions!D36, Construction!G33, TBA!F14 |
| Construction!G43 | Construction\|43\|Construction!r2 | Y3 | same_period | G16-G28<0.01 | Construction!G16, Construction!G28 |
| Construction!G6 | Construction\|6\|Construction!r2 | Y3 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!F8 | Input Assumptions!D25, Input Assumptions!D9, TBA!F8 |
| Construction!G8 | Construction\|8\|Construction!r2 | Y3 | aggregation | SUM(G6:G7) | Construction!G6:G7 |
| Construction!H12 | Construction\|12\|Construction!r2 | Y4 | same_period | H8 | Construction!H8 |
| Construction!H13 | Construction\|13\|Construction!r2 | Y4 | same_period | H37 | Construction!H37 |
| Construction!H14 | Construction\|14\|Construction!r2 | Y4 | same_period | H38 | Construction!H38 |
| Construction!H15 | Construction\|15\|Construction!r2 | Y4 | same_period | H39 | Construction!H39 |
| Construction!H16 | Construction\|16\|Construction!r2 | Y4 | aggregation | SUM(H12:H15) | Construction!H12:H15 |
| Construction!H26 | Construction\|26\|Construction!r2 | Y4 | conditional | IF(MAX($C$22-SUM($D$26:G26),0)>H19,H19,MAX($C$22-SUM($D$26:G26),0)) | Construction!C22, Construction!D26:G26, Construction!H19 |
| Construction!H27 | Construction\|27\|Construction!r2 | Y4 | conditional | IF(H19-H26>0,H19-H26,0) | Construction!H19, Construction!H26 |
| Construction!H28 | Construction\|28\|Construction!r2 | Y4 | aggregation | SUM(H26:H27) | Construction!H26:H27 |
| Construction!H33 | Construction\|33\|Construction!r2 | Y4 | rollforward | G35 | Construction!G35 |
| Construction!H34 | Construction\|34\|Construction!r2 | Y4 | same_period | H27 | Construction!H27 |
| Construction!H35 | Construction\|35\|Construction!r2 | Y4 | aggregation | SUM(H33:H34) | Construction!H33:H34 |
| Construction!H37 | Construction\|37\|Construction!r2 | Y4 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!G13 | Input Assumptions!D37, Construction!C34, TBA!G13 |
| Construction!H38 | Construction\|38\|Construction!r2 | Y4 | same_period | ($C$34-H33)*TBA!G14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!H33, TBA!G14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!H39 | Construction\|39\|Construction!r2 | Y4 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*H33*TBA!G14 | Input Assumptions!D35, Input Assumptions!D36, Construction!H33, TBA!G14 |
| Construction!H43 | Construction\|43\|Construction!r2 | Y4 | same_period | H16-H28<0.01 | Construction!H16, Construction!H28 |
| Construction!H6 | Construction\|6\|Construction!r2 | Y4 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!G8 | Input Assumptions!D25, Input Assumptions!D9, TBA!G8 |
| Construction!H8 | Construction\|8\|Construction!r2 | Y4 | aggregation | SUM(H6:H7) | Construction!H6:H7 |
| Construction!I12 | Construction\|12\|Construction!r2 | Y5 | same_period | I8 | Construction!I8 |
| Construction!I13 | Construction\|13\|Construction!r2 | Y5 | same_period | I37 | Construction!I37 |
| Construction!I14 | Construction\|14\|Construction!r2 | Y5 | same_period | I38 | Construction!I38 |
| Construction!I15 | Construction\|15\|Construction!r2 | Y5 | same_period | I39 | Construction!I39 |
| Construction!I16 | Construction\|16\|Construction!r2 | Y5 | aggregation | SUM(I12:I15) | Construction!I12:I15 |
| Construction!I26 | Construction\|26\|Construction!r2 | Y5 | conditional | IF(MAX($C$22-SUM($D$26:H26),0)>I19,I19,MAX($C$22-SUM($D$26:H26),0)) | Construction!C22, Construction!D26:H26, Construction!I19 |
| Construction!I27 | Construction\|27\|Construction!r2 | Y5 | conditional | IF(I19-I26>0,I19-I26,0) | Construction!I19, Construction!I26 |
| Construction!I28 | Construction\|28\|Construction!r2 | Y5 | aggregation | SUM(I26:I27) | Construction!I26:I27 |
| Construction!I33 | Construction\|33\|Construction!r2 | Y5 | rollforward | H35 | Construction!H35 |
| Construction!I34 | Construction\|34\|Construction!r2 | Y5 | same_period | I27 | Construction!I27 |
| Construction!I35 | Construction\|35\|Construction!r2 | Y5 | aggregation | SUM(I33:I34) | Construction!I33:I34 |
| Construction!I37 | Construction\|37\|Construction!r2 | Y5 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!H13 | Input Assumptions!D37, Construction!C34, TBA!H13 |
| Construction!I38 | Construction\|38\|Construction!r2 | Y5 | same_period | ($C$34-I33)*TBA!H14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!I33, TBA!H14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!I39 | Construction\|39\|Construction!r2 | Y5 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*I33*TBA!H14 | Input Assumptions!D35, Input Assumptions!D36, Construction!I33, TBA!H14 |
| Construction!I43 | Construction\|43\|Construction!r2 | Y5 | same_period | I16-I28<0.01 | Construction!I16, Construction!I28 |
| Construction!I6 | Construction\|6\|Construction!r2 | Y5 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!H8 | Input Assumptions!D25, Input Assumptions!D9, TBA!H8 |
| Construction!I8 | Construction\|8\|Construction!r2 | Y5 | aggregation | SUM(I6:I7) | Construction!I6:I7 |
| Construction!J12 | Construction\|12\|Construction!r2 | Y6 | same_period | J8 | Construction!J8 |
| Construction!J13 | Construction\|13\|Construction!r2 | Y6 | same_period | J37 | Construction!J37 |
| Construction!J14 | Construction\|14\|Construction!r2 | Y6 | same_period | J38 | Construction!J38 |
| Construction!J15 | Construction\|15\|Construction!r2 | Y6 | same_period | J39 | Construction!J39 |
| Construction!J16 | Construction\|16\|Construction!r2 | Y6 | aggregation | SUM(J12:J15) | Construction!J12:J15 |
| Construction!J26 | Construction\|26\|Construction!r2 | Y6 | conditional | IF(MAX($C$22-SUM($D$26:I26),0)>J19,J19,MAX($C$22-SUM($D$26:I26),0)) | Construction!C22, Construction!D26:I26, Construction!J19 |
| Construction!J27 | Construction\|27\|Construction!r2 | Y6 | conditional | IF(J19-J26>0,J19-J26,0) | Construction!J19, Construction!J26 |
| Construction!J28 | Construction\|28\|Construction!r2 | Y6 | aggregation | SUM(J26:J27) | Construction!J26:J27 |
| Construction!J33 | Construction\|33\|Construction!r2 | Y6 | rollforward | I35 | Construction!I35 |
| Construction!J34 | Construction\|34\|Construction!r2 | Y6 | same_period | J27 | Construction!J27 |
| Construction!J35 | Construction\|35\|Construction!r2 | Y6 | aggregation | SUM(J33:J34) | Construction!J33:J34 |
| Construction!J37 | Construction\|37\|Construction!r2 | Y6 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!I13 | Input Assumptions!D37, Construction!C34, TBA!I13 |
| Construction!J38 | Construction\|38\|Construction!r2 | Y6 | same_period | ($C$34-J33)*TBA!I14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!J33, TBA!I14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!J39 | Construction\|39\|Construction!r2 | Y6 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*J33*TBA!I14 | Input Assumptions!D35, Input Assumptions!D36, Construction!J33, TBA!I14 |
| Construction!J43 | Construction\|43\|Construction!r2 | Y6 | same_period | J16-J28<0.01 | Construction!J16, Construction!J28 |
| Construction!J6 | Construction\|6\|Construction!r2 | Y6 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!I8 | Input Assumptions!D25, Input Assumptions!D9, TBA!I8 |
| Construction!J8 | Construction\|8\|Construction!r2 | Y6 | aggregation | SUM(J6:J7) | Construction!J6:J7 |
| Construction!K12 | Construction\|12\|Construction!r2 | Y7 | same_period | K8 | Construction!K8 |
| Construction!K13 | Construction\|13\|Construction!r2 | Y7 | same_period | K37 | Construction!K37 |
| Construction!K14 | Construction\|14\|Construction!r2 | Y7 | same_period | K38 | Construction!K38 |
| Construction!K15 | Construction\|15\|Construction!r2 | Y7 | same_period | K39 | Construction!K39 |
| Construction!K16 | Construction\|16\|Construction!r2 | Y7 | aggregation | SUM(K12:K15) | Construction!K12:K15 |
| Construction!K26 | Construction\|26\|Construction!r2 | Y7 | conditional | IF(MAX($C$22-SUM($D$26:J26),0)>K19,K19,MAX($C$22-SUM($D$26:J26),0)) | Construction!C22, Construction!D26:J26, Construction!K19 |
| Construction!K27 | Construction\|27\|Construction!r2 | Y7 | conditional | IF(K19-K26>0,K19-K26,0) | Construction!K19, Construction!K26 |
| Construction!K28 | Construction\|28\|Construction!r2 | Y7 | aggregation | SUM(K26:K27) | Construction!K26:K27 |
| Construction!K33 | Construction\|33\|Construction!r2 | Y7 | rollforward | J35 | Construction!J35 |
| Construction!K34 | Construction\|34\|Construction!r2 | Y7 | same_period | K27 | Construction!K27 |
| Construction!K35 | Construction\|35\|Construction!r2 | Y7 | aggregation | SUM(K33:K34) | Construction!K33:K34 |
| Construction!K37 | Construction\|37\|Construction!r2 | Y7 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!J13 | Input Assumptions!D37, Construction!C34, TBA!J13 |
| Construction!K38 | Construction\|38\|Construction!r2 | Y7 | same_period | ($C$34-K33)*TBA!J14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!K33, TBA!J14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!K39 | Construction\|39\|Construction!r2 | Y7 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*K33*TBA!J14 | Input Assumptions!D35, Input Assumptions!D36, Construction!K33, TBA!J14 |
| Construction!K43 | Construction\|43\|Construction!r2 | Y7 | same_period | K16-K28<0.01 | Construction!K16, Construction!K28 |
| Construction!K6 | Construction\|6\|Construction!r2 | Y7 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!J8 | Input Assumptions!D25, Input Assumptions!D9, TBA!J8 |
| Construction!K8 | Construction\|8\|Construction!r2 | Y7 | aggregation | SUM(K6:K7) | Construction!K6:K7 |
| Construction!L12 | Construction\|12\|Construction!r2 | Y8 | same_period | L8 | Construction!L8 |
| Construction!L13 | Construction\|13\|Construction!r2 | Y8 | same_period | L37 | Construction!L37 |
| Construction!L14 | Construction\|14\|Construction!r2 | Y8 | same_period | L38 | Construction!L38 |
| Construction!L15 | Construction\|15\|Construction!r2 | Y8 | same_period | L39 | Construction!L39 |
| Construction!L16 | Construction\|16\|Construction!r2 | Y8 | aggregation | SUM(L12:L15) | Construction!L12:L15 |
| Construction!L26 | Construction\|26\|Construction!r2 | Y8 | conditional | IF(MAX($C$22-SUM($D$26:K26),0)>L19,L19,MAX($C$22-SUM($D$26:K26),0)) | Construction!C22, Construction!D26:K26, Construction!L19 |
| Construction!L27 | Construction\|27\|Construction!r2 | Y8 | conditional | IF(L19-L26>0,L19-L26,0) | Construction!L19, Construction!L26 |
| Construction!L28 | Construction\|28\|Construction!r2 | Y8 | aggregation | SUM(L26:L27) | Construction!L26:L27 |
| Construction!L33 | Construction\|33\|Construction!r2 | Y8 | rollforward | K35 | Construction!K35 |
| Construction!L34 | Construction\|34\|Construction!r2 | Y8 | same_period | L27 | Construction!L27 |
| Construction!L35 | Construction\|35\|Construction!r2 | Y8 | aggregation | SUM(L33:L34) | Construction!L33:L34 |
| Construction!L37 | Construction\|37\|Construction!r2 | Y8 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!K13 | Input Assumptions!D37, Construction!C34, TBA!K13 |
| Construction!L38 | Construction\|38\|Construction!r2 | Y8 | same_period | ($C$34-L33)*TBA!K14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!L33, TBA!K14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!L39 | Construction\|39\|Construction!r2 | Y8 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*L33*TBA!K14 | Input Assumptions!D35, Input Assumptions!D36, Construction!L33, TBA!K14 |
| Construction!L43 | Construction\|43\|Construction!r2 | Y8 | same_period | L16-L28<0.01 | Construction!L16, Construction!L28 |
| Construction!L6 | Construction\|6\|Construction!r2 | Y8 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!K8 | Input Assumptions!D25, Input Assumptions!D9, TBA!K8 |
| Construction!L8 | Construction\|8\|Construction!r2 | Y8 | aggregation | SUM(L6:L7) | Construction!L6:L7 |
| Construction!M12 | Construction\|12\|Construction!r2 | Y9 | same_period | M8 | Construction!M8 |
| Construction!M13 | Construction\|13\|Construction!r2 | Y9 | same_period | M37 | Construction!M37 |
| Construction!M14 | Construction\|14\|Construction!r2 | Y9 | same_period | M38 | Construction!M38 |
| Construction!M15 | Construction\|15\|Construction!r2 | Y9 | same_period | M39 | Construction!M39 |
| Construction!M16 | Construction\|16\|Construction!r2 | Y9 | aggregation | SUM(M12:M15) | Construction!M12:M15 |
| Construction!M26 | Construction\|26\|Construction!r2 | Y9 | conditional | IF(MAX($C$22-SUM($D$26:L26),0)>M19,M19,MAX($C$22-SUM($D$26:L26),0)) | Construction!C22, Construction!D26:L26, Construction!M19 |
| Construction!M27 | Construction\|27\|Construction!r2 | Y9 | conditional | IF(M19-M26>0,M19-M26,0) | Construction!M19, Construction!M26 |
| Construction!M28 | Construction\|28\|Construction!r2 | Y9 | aggregation | SUM(M26:M27) | Construction!M26:M27 |
| Construction!M33 | Construction\|33\|Construction!r2 | Y9 | rollforward | L35 | Construction!L35 |
| Construction!M34 | Construction\|34\|Construction!r2 | Y9 | same_period | M27 | Construction!M27 |
| Construction!M35 | Construction\|35\|Construction!r2 | Y9 | aggregation | SUM(M33:M34) | Construction!M33:M34 |
| Construction!M37 | Construction\|37\|Construction!r2 | Y9 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!L13 | Input Assumptions!D37, Construction!C34, TBA!L13 |
| Construction!M38 | Construction\|38\|Construction!r2 | Y9 | same_period | ($C$34-M33)*TBA!L14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!M33, TBA!L14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!M39 | Construction\|39\|Construction!r2 | Y9 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*M33*TBA!L14 | Input Assumptions!D35, Input Assumptions!D36, Construction!M33, TBA!L14 |
| Construction!M43 | Construction\|43\|Construction!r2 | Y9 | same_period | M16-M28<0.01 | Construction!M16, Construction!M28 |
| Construction!M6 | Construction\|6\|Construction!r2 | Y9 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!L8 | Input Assumptions!D25, Input Assumptions!D9, TBA!L8 |
| Construction!M8 | Construction\|8\|Construction!r2 | Y9 | aggregation | SUM(M6:M7) | Construction!M6:M7 |
| Construction!N12 | Construction\|12\|Construction!r2 | Y10 | same_period | N8 | Construction!N8 |
| Construction!N13 | Construction\|13\|Construction!r2 | Y10 | same_period | N37 | Construction!N37 |
| Construction!N14 | Construction\|14\|Construction!r2 | Y10 | same_period | N38 | Construction!N38 |
| Construction!N15 | Construction\|15\|Construction!r2 | Y10 | same_period | N39 | Construction!N39 |
| Construction!N16 | Construction\|16\|Construction!r2 | Y10 | aggregation | SUM(N12:N15) | Construction!N12:N15 |
| Construction!N26 | Construction\|26\|Construction!r2 | Y10 | conditional | IF(MAX($C$22-SUM($D$26:M26),0)>N19,N19,MAX($C$22-SUM($D$26:M26),0)) | Construction!C22, Construction!D26:M26, Construction!N19 |
| Construction!N27 | Construction\|27\|Construction!r2 | Y10 | conditional | IF(N19-N26>0,N19-N26,0) | Construction!N19, Construction!N26 |
| Construction!N28 | Construction\|28\|Construction!r2 | Y10 | aggregation | SUM(N26:N27) | Construction!N26:N27 |
| Construction!N33 | Construction\|33\|Construction!r2 | Y10 | rollforward | M35 | Construction!M35 |
| Construction!N34 | Construction\|34\|Construction!r2 | Y10 | same_period | N27 | Construction!N27 |
| Construction!N35 | Construction\|35\|Construction!r2 | Y10 | aggregation | SUM(N33:N34) | Construction!N33:N34 |
| Construction!N37 | Construction\|37\|Construction!r2 | Y10 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!M13 | Input Assumptions!D37, Construction!C34, TBA!M13 |
| Construction!N38 | Construction\|38\|Construction!r2 | Y10 | same_period | ($C$34-N33)*TBA!M14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!N33, TBA!M14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!N39 | Construction\|39\|Construction!r2 | Y10 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*N33*TBA!M14 | Input Assumptions!D35, Input Assumptions!D36, Construction!N33, TBA!M14 |
| Construction!N43 | Construction\|43\|Construction!r2 | Y10 | same_period | N16-N28<0.01 | Construction!N16, Construction!N28 |
| Construction!N6 | Construction\|6\|Construction!r2 | Y10 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!M8 | Input Assumptions!D25, Input Assumptions!D9, TBA!M8 |
| Construction!N8 | Construction\|8\|Construction!r2 | Y10 | aggregation | SUM(N6:N7) | Construction!N6:N7 |
| Construction!O12 | Construction\|12\|Construction!r2 | Y11 | same_period | O8 | Construction!O8 |
| Construction!O13 | Construction\|13\|Construction!r2 | Y11 | same_period | O37 | Construction!O37 |
| Construction!O14 | Construction\|14\|Construction!r2 | Y11 | same_period | O38 | Construction!O38 |
| Construction!O15 | Construction\|15\|Construction!r2 | Y11 | same_period | O39 | Construction!O39 |
| Construction!O16 | Construction\|16\|Construction!r2 | Y11 | aggregation | SUM(O12:O15) | Construction!O12:O15 |
| Construction!O26 | Construction\|26\|Construction!r2 | Y11 | conditional | IF(MAX($C$22-SUM($D$26:N26),0)>O19,O19,MAX($C$22-SUM($D$26:N26),0)) | Construction!C22, Construction!D26:N26, Construction!O19 |
| Construction!O27 | Construction\|27\|Construction!r2 | Y11 | conditional | IF(O19-O26>0,O19-O26,0) | Construction!O19, Construction!O26 |
| Construction!O28 | Construction\|28\|Construction!r2 | Y11 | aggregation | SUM(O26:O27) | Construction!O26:O27 |
| Construction!O33 | Construction\|33\|Construction!r2 | Y11 | rollforward | N35 | Construction!N35 |
| Construction!O34 | Construction\|34\|Construction!r2 | Y11 | same_period | O27 | Construction!O27 |
| Construction!O35 | Construction\|35\|Construction!r2 | Y11 | aggregation | SUM(O33:O34) | Construction!O33:O34 |
| Construction!O37 | Construction\|37\|Construction!r2 | Y11 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!N13 | Input Assumptions!D37, Construction!C34, TBA!N13 |
| Construction!O38 | Construction\|38\|Construction!r2 | Y11 | same_period | ($C$34-O33)*TBA!N14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!O33, TBA!N14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!O39 | Construction\|39\|Construction!r2 | Y11 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*O33*TBA!N14 | Input Assumptions!D35, Input Assumptions!D36, Construction!O33, TBA!N14 |
| Construction!O43 | Construction\|43\|Construction!r2 | Y11 | same_period | O16-O28<0.01 | Construction!O16, Construction!O28 |
| Construction!O6 | Construction\|6\|Construction!r2 | Y11 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!N8 | Input Assumptions!D25, Input Assumptions!D9, TBA!N8 |
| Construction!O8 | Construction\|8\|Construction!r2 | Y11 | aggregation | SUM(O6:O7) | Construction!O6:O7 |
| Construction!P12 | Construction\|12\|Construction!r2 | Y12 | same_period | P8 | Construction!P8 |
| Construction!P13 | Construction\|13\|Construction!r2 | Y12 | same_period | P37 | Construction!P37 |
| Construction!P14 | Construction\|14\|Construction!r2 | Y12 | same_period | P38 | Construction!P38 |
| Construction!P15 | Construction\|15\|Construction!r2 | Y12 | same_period | P39 | Construction!P39 |
| Construction!P16 | Construction\|16\|Construction!r2 | Y12 | aggregation | SUM(P12:P15) | Construction!P12:P15 |
| Construction!P26 | Construction\|26\|Construction!r2 | Y12 | conditional | IF(MAX($C$22-SUM($D$26:O26),0)>P19,P19,MAX($C$22-SUM($D$26:O26),0)) | Construction!C22, Construction!D26:O26, Construction!P19 |
| Construction!P27 | Construction\|27\|Construction!r2 | Y12 | conditional | IF(P19-P26>0,P19-P26,0) | Construction!P19, Construction!P26 |
| Construction!P28 | Construction\|28\|Construction!r2 | Y12 | aggregation | SUM(P26:P27) | Construction!P26:P27 |
| Construction!P33 | Construction\|33\|Construction!r2 | Y12 | rollforward | O35 | Construction!O35 |
| Construction!P34 | Construction\|34\|Construction!r2 | Y12 | same_period | P27 | Construction!P27 |
| Construction!P35 | Construction\|35\|Construction!r2 | Y12 | aggregation | SUM(P33:P34) | Construction!P33:P34 |
| Construction!P37 | Construction\|37\|Construction!r2 | Y12 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!O13 | Input Assumptions!D37, Construction!C34, TBA!O13 |
| Construction!P38 | Construction\|38\|Construction!r2 | Y12 | same_period | ($C$34-P33)*TBA!O14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!P33, TBA!O14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!P39 | Construction\|39\|Construction!r2 | Y12 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*P33*TBA!O14 | Input Assumptions!D35, Input Assumptions!D36, Construction!P33, TBA!O14 |
| Construction!P43 | Construction\|43\|Construction!r2 | Y12 | same_period | P16-P28<0.01 | Construction!P16, Construction!P28 |
| Construction!P6 | Construction\|6\|Construction!r2 | Y12 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!O8 | Input Assumptions!D25, Input Assumptions!D9, TBA!O8 |
| Construction!P8 | Construction\|8\|Construction!r2 | Y12 | aggregation | SUM(P6:P7) | Construction!P6:P7 |
| Construction!Q12 | Construction\|12\|Construction!r2 | Y13 | same_period | Q8 | Construction!Q8 |
| Construction!Q13 | Construction\|13\|Construction!r2 | Y13 | same_period | Q37 | Construction!Q37 |
| Construction!Q14 | Construction\|14\|Construction!r2 | Y13 | same_period | Q38 | Construction!Q38 |
| Construction!Q15 | Construction\|15\|Construction!r2 | Y13 | same_period | Q39 | Construction!Q39 |
| Construction!Q16 | Construction\|16\|Construction!r2 | Y13 | aggregation | SUM(Q12:Q15) | Construction!Q12:Q15 |
| Construction!Q26 | Construction\|26\|Construction!r2 | Y13 | conditional | IF(MAX($C$22-SUM($D$26:P26),0)>Q19,Q19,MAX($C$22-SUM($D$26:P26),0)) | Construction!C22, Construction!D26:P26, Construction!Q19 |
| Construction!Q27 | Construction\|27\|Construction!r2 | Y13 | conditional | IF(Q19-Q26>0,Q19-Q26,0) | Construction!Q19, Construction!Q26 |
| Construction!Q28 | Construction\|28\|Construction!r2 | Y13 | aggregation | SUM(Q26:Q27) | Construction!Q26:Q27 |
| Construction!Q33 | Construction\|33\|Construction!r2 | Y13 | rollforward | P35 | Construction!P35 |
| Construction!Q34 | Construction\|34\|Construction!r2 | Y13 | same_period | Q27 | Construction!Q27 |
| Construction!Q35 | Construction\|35\|Construction!r2 | Y13 | aggregation | SUM(Q33:Q34) | Construction!Q33:Q34 |
| Construction!Q37 | Construction\|37\|Construction!r2 | Y13 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!P13 | Input Assumptions!D37, Construction!C34, TBA!P13 |
| Construction!Q38 | Construction\|38\|Construction!r2 | Y13 | same_period | ($C$34-Q33)*TBA!P14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!Q33, TBA!P14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!Q39 | Construction\|39\|Construction!r2 | Y13 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Q33*TBA!P14 | Input Assumptions!D35, Input Assumptions!D36, Construction!Q33, TBA!P14 |
| Construction!Q43 | Construction\|43\|Construction!r2 | Y13 | same_period | Q16-Q28<0.01 | Construction!Q16, Construction!Q28 |
| Construction!Q6 | Construction\|6\|Construction!r2 | Y13 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!P8 | Input Assumptions!D25, Input Assumptions!D9, TBA!P8 |
| Construction!Q8 | Construction\|8\|Construction!r2 | Y13 | aggregation | SUM(Q6:Q7) | Construction!Q6:Q7 |
| Construction!R12 | Construction\|12\|Construction!r2 | Y14 | same_period | R8 | Construction!R8 |
| Construction!R13 | Construction\|13\|Construction!r2 | Y14 | same_period | R37 | Construction!R37 |
| Construction!R14 | Construction\|14\|Construction!r2 | Y14 | same_period | R38 | Construction!R38 |
| Construction!R15 | Construction\|15\|Construction!r2 | Y14 | same_period | R39 | Construction!R39 |
| Construction!R16 | Construction\|16\|Construction!r2 | Y14 | aggregation | SUM(R12:R15) | Construction!R12:R15 |
| Construction!R26 | Construction\|26\|Construction!r2 | Y14 | conditional | IF(MAX($C$22-SUM($D$26:Q26),0)>R19,R19,MAX($C$22-SUM($D$26:Q26),0)) | Construction!C22, Construction!D26:Q26, Construction!R19 |
| Construction!R27 | Construction\|27\|Construction!r2 | Y14 | conditional | IF(R19-R26>0,R19-R26,0) | Construction!R19, Construction!R26 |
| Construction!R28 | Construction\|28\|Construction!r2 | Y14 | aggregation | SUM(R26:R27) | Construction!R26:R27 |
| Construction!R33 | Construction\|33\|Construction!r2 | Y14 | rollforward | Q35 | Construction!Q35 |
| Construction!R34 | Construction\|34\|Construction!r2 | Y14 | same_period | R27 | Construction!R27 |
| Construction!R35 | Construction\|35\|Construction!r2 | Y14 | aggregation | SUM(R33:R34) | Construction!R33:R34 |
| Construction!R37 | Construction\|37\|Construction!r2 | Y14 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!Q13 | Input Assumptions!D37, Construction!C34, TBA!Q13 |
| Construction!R38 | Construction\|38\|Construction!r2 | Y14 | same_period | ($C$34-R33)*TBA!Q14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!R33, TBA!Q14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!R39 | Construction\|39\|Construction!r2 | Y14 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*R33*TBA!Q14 | Input Assumptions!D35, Input Assumptions!D36, Construction!R33, TBA!Q14 |
| Construction!R43 | Construction\|43\|Construction!r2 | Y14 | same_period | R16-R28<0.01 | Construction!R16, Construction!R28 |
| Construction!R6 | Construction\|6\|Construction!r2 | Y14 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!Q8 | Input Assumptions!D25, Input Assumptions!D9, TBA!Q8 |
| Construction!R8 | Construction\|8\|Construction!r2 | Y14 | aggregation | SUM(R6:R7) | Construction!R6:R7 |
| Construction!S12 | Construction\|12\|Construction!r2 | Y15 | same_period | S8 | Construction!S8 |
| Construction!S13 | Construction\|13\|Construction!r2 | Y15 | same_period | S37 | Construction!S37 |
| Construction!S14 | Construction\|14\|Construction!r2 | Y15 | same_period | S38 | Construction!S38 |
| Construction!S15 | Construction\|15\|Construction!r2 | Y15 | same_period | S39 | Construction!S39 |
| Construction!S16 | Construction\|16\|Construction!r2 | Y15 | aggregation | SUM(S12:S15) | Construction!S12:S15 |
| Construction!S26 | Construction\|26\|Construction!r2 | Y15 | conditional | IF(MAX($C$22-SUM($D$26:R26),0)>S19,S19,MAX($C$22-SUM($D$26:R26),0)) | Construction!C22, Construction!D26:R26, Construction!S19 |
| Construction!S27 | Construction\|27\|Construction!r2 | Y15 | conditional | IF(S19-S26>0,S19-S26,0) | Construction!S19, Construction!S26 |
| Construction!S28 | Construction\|28\|Construction!r2 | Y15 | aggregation | SUM(S26:S27) | Construction!S26:S27 |
| Construction!S33 | Construction\|33\|Construction!r2 | Y15 | rollforward | R35 | Construction!R35 |
| Construction!S34 | Construction\|34\|Construction!r2 | Y15 | same_period | S27 | Construction!S27 |
| Construction!S35 | Construction\|35\|Construction!r2 | Y15 | aggregation | SUM(S33:S34) | Construction!S33:S34 |
| Construction!S37 | Construction\|37\|Construction!r2 | Y15 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!R13 | Input Assumptions!D37, Construction!C34, TBA!R13 |
| Construction!S38 | Construction\|38\|Construction!r2 | Y15 | same_period | ($C$34-S33)*TBA!R14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!S33, TBA!R14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!S39 | Construction\|39\|Construction!r2 | Y15 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*S33*TBA!R14 | Input Assumptions!D35, Input Assumptions!D36, Construction!S33, TBA!R14 |
| Construction!S43 | Construction\|43\|Construction!r2 | Y15 | same_period | S16-S28<0.01 | Construction!S16, Construction!S28 |
| Construction!S6 | Construction\|6\|Construction!r2 | Y15 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!R8 | Input Assumptions!D25, Input Assumptions!D9, TBA!R8 |
| Construction!S8 | Construction\|8\|Construction!r2 | Y15 | aggregation | SUM(S6:S7) | Construction!S6:S7 |
| Construction!T12 | Construction\|12\|Construction!r2 | Y16 | same_period | T8 | Construction!T8 |
| Construction!T13 | Construction\|13\|Construction!r2 | Y16 | same_period | T37 | Construction!T37 |
| Construction!T14 | Construction\|14\|Construction!r2 | Y16 | same_period | T38 | Construction!T38 |
| Construction!T15 | Construction\|15\|Construction!r2 | Y16 | same_period | T39 | Construction!T39 |
| Construction!T16 | Construction\|16\|Construction!r2 | Y16 | aggregation | SUM(T12:T15) | Construction!T12:T15 |
| Construction!T26 | Construction\|26\|Construction!r2 | Y16 | conditional | IF(MAX($C$22-SUM($D$26:S26),0)>T19,T19,MAX($C$22-SUM($D$26:S26),0)) | Construction!C22, Construction!D26:S26, Construction!T19 |
| Construction!T27 | Construction\|27\|Construction!r2 | Y16 | conditional | IF(T19-T26>0,T19-T26,0) | Construction!T19, Construction!T26 |
| Construction!T28 | Construction\|28\|Construction!r2 | Y16 | aggregation | SUM(T26:T27) | Construction!T26:T27 |
| Construction!T33 | Construction\|33\|Construction!r2 | Y16 | rollforward | S35 | Construction!S35 |
| Construction!T34 | Construction\|34\|Construction!r2 | Y16 | same_period | T27 | Construction!T27 |
| Construction!T35 | Construction\|35\|Construction!r2 | Y16 | aggregation | SUM(T33:T34) | Construction!T33:T34 |
| Construction!T37 | Construction\|37\|Construction!r2 | Y16 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!S13 | Input Assumptions!D37, Construction!C34, TBA!S13 |
| Construction!T38 | Construction\|38\|Construction!r2 | Y16 | same_period | ($C$34-T33)*TBA!S14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!T33, TBA!S14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!T39 | Construction\|39\|Construction!r2 | Y16 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*T33*TBA!S14 | Input Assumptions!D35, Input Assumptions!D36, Construction!T33, TBA!S14 |
| Construction!T43 | Construction\|43\|Construction!r2 | Y16 | same_period | T16-T28<0.01 | Construction!T16, Construction!T28 |
| Construction!T6 | Construction\|6\|Construction!r2 | Y16 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!S8 | Input Assumptions!D25, Input Assumptions!D9, TBA!S8 |
| Construction!T8 | Construction\|8\|Construction!r2 | Y16 | aggregation | SUM(T6:T7) | Construction!T6:T7 |
| Construction!U12 | Construction\|12\|Construction!r2 | Y17 | same_period | U8 | Construction!U8 |
| Construction!U13 | Construction\|13\|Construction!r2 | Y17 | same_period | U37 | Construction!U37 |
| Construction!U14 | Construction\|14\|Construction!r2 | Y17 | same_period | U38 | Construction!U38 |
| Construction!U15 | Construction\|15\|Construction!r2 | Y17 | same_period | U39 | Construction!U39 |
| Construction!U16 | Construction\|16\|Construction!r2 | Y17 | aggregation | SUM(U12:U15) | Construction!U12:U15 |
| Construction!U26 | Construction\|26\|Construction!r2 | Y17 | conditional | IF(MAX($C$22-SUM($D$26:T26),0)>U19,U19,MAX($C$22-SUM($D$26:T26),0)) | Construction!C22, Construction!D26:T26, Construction!U19 |
| Construction!U27 | Construction\|27\|Construction!r2 | Y17 | conditional | IF(U19-U26>0,U19-U26,0) | Construction!U19, Construction!U26 |
| Construction!U28 | Construction\|28\|Construction!r2 | Y17 | aggregation | SUM(U26:U27) | Construction!U26:U27 |
| Construction!U33 | Construction\|33\|Construction!r2 | Y17 | rollforward | T35 | Construction!T35 |
| Construction!U34 | Construction\|34\|Construction!r2 | Y17 | same_period | U27 | Construction!U27 |
| Construction!U35 | Construction\|35\|Construction!r2 | Y17 | aggregation | SUM(U33:U34) | Construction!U33:U34 |
| Construction!U37 | Construction\|37\|Construction!r2 | Y17 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!T13 | Input Assumptions!D37, Construction!C34, TBA!T13 |
| Construction!U38 | Construction\|38\|Construction!r2 | Y17 | same_period | ($C$34-U33)*TBA!T14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!U33, TBA!T14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!U39 | Construction\|39\|Construction!r2 | Y17 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*U33*TBA!T14 | Input Assumptions!D35, Input Assumptions!D36, Construction!U33, TBA!T14 |
| Construction!U43 | Construction\|43\|Construction!r2 | Y17 | same_period | U16-U28<0.01 | Construction!U16, Construction!U28 |
| Construction!U6 | Construction\|6\|Construction!r2 | Y17 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!T8 | Input Assumptions!D25, Input Assumptions!D9, TBA!T8 |
| Construction!U8 | Construction\|8\|Construction!r2 | Y17 | aggregation | SUM(U6:U7) | Construction!U6:U7 |
| Construction!V12 | Construction\|12\|Construction!r2 | Y18 | same_period | V8 | Construction!V8 |
| Construction!V13 | Construction\|13\|Construction!r2 | Y18 | same_period | V37 | Construction!V37 |
| Construction!V14 | Construction\|14\|Construction!r2 | Y18 | same_period | V38 | Construction!V38 |
| Construction!V15 | Construction\|15\|Construction!r2 | Y18 | same_period | V39 | Construction!V39 |
| Construction!V16 | Construction\|16\|Construction!r2 | Y18 | aggregation | SUM(V12:V15) | Construction!V12:V15 |
| Construction!V26 | Construction\|26\|Construction!r2 | Y18 | conditional | IF(MAX($C$22-SUM($D$26:U26),0)>V19,V19,MAX($C$22-SUM($D$26:U26),0)) | Construction!C22, Construction!D26:U26, Construction!V19 |
| Construction!V27 | Construction\|27\|Construction!r2 | Y18 | conditional | IF(V19-V26>0,V19-V26,0) | Construction!V19, Construction!V26 |
| Construction!V28 | Construction\|28\|Construction!r2 | Y18 | aggregation | SUM(V26:V27) | Construction!V26:V27 |
| Construction!V33 | Construction\|33\|Construction!r2 | Y18 | rollforward | U35 | Construction!U35 |
| Construction!V34 | Construction\|34\|Construction!r2 | Y18 | same_period | V27 | Construction!V27 |
| Construction!V35 | Construction\|35\|Construction!r2 | Y18 | aggregation | SUM(V33:V34) | Construction!V33:V34 |
| Construction!V37 | Construction\|37\|Construction!r2 | Y18 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!U13 | Input Assumptions!D37, Construction!C34, TBA!U13 |
| Construction!V38 | Construction\|38\|Construction!r2 | Y18 | same_period | ($C$34-V33)*TBA!U14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!V33, TBA!U14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!V39 | Construction\|39\|Construction!r2 | Y18 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*V33*TBA!U14 | Input Assumptions!D35, Input Assumptions!D36, Construction!V33, TBA!U14 |
| Construction!V43 | Construction\|43\|Construction!r2 | Y18 | same_period | V16-V28<0.01 | Construction!V16, Construction!V28 |
| Construction!V6 | Construction\|6\|Construction!r2 | Y18 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!U8 | Input Assumptions!D25, Input Assumptions!D9, TBA!U8 |
| Construction!V8 | Construction\|8\|Construction!r2 | Y18 | aggregation | SUM(V6:V7) | Construction!V6:V7 |
| Construction!W12 | Construction\|12\|Construction!r2 | Y19 | same_period | W8 | Construction!W8 |
| Construction!W13 | Construction\|13\|Construction!r2 | Y19 | same_period | W37 | Construction!W37 |
| Construction!W14 | Construction\|14\|Construction!r2 | Y19 | same_period | W38 | Construction!W38 |
| Construction!W15 | Construction\|15\|Construction!r2 | Y19 | same_period | W39 | Construction!W39 |
| Construction!W16 | Construction\|16\|Construction!r2 | Y19 | aggregation | SUM(W12:W15) | Construction!W12:W15 |
| Construction!W26 | Construction\|26\|Construction!r2 | Y19 | conditional | IF(MAX($C$22-SUM($D$26:V26),0)>W19,W19,MAX($C$22-SUM($D$26:V26),0)) | Construction!C22, Construction!D26:V26, Construction!W19 |
| Construction!W27 | Construction\|27\|Construction!r2 | Y19 | conditional | IF(W19-W26>0,W19-W26,0) | Construction!W19, Construction!W26 |
| Construction!W28 | Construction\|28\|Construction!r2 | Y19 | aggregation | SUM(W26:W27) | Construction!W26:W27 |
| Construction!W33 | Construction\|33\|Construction!r2 | Y19 | rollforward | V35 | Construction!V35 |
| Construction!W34 | Construction\|34\|Construction!r2 | Y19 | same_period | W27 | Construction!W27 |
| Construction!W35 | Construction\|35\|Construction!r2 | Y19 | aggregation | SUM(W33:W34) | Construction!W33:W34 |
| Construction!W37 | Construction\|37\|Construction!r2 | Y19 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!V13 | Input Assumptions!D37, Construction!C34, TBA!V13 |
| Construction!W38 | Construction\|38\|Construction!r2 | Y19 | same_period | ($C$34-W33)*TBA!V14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!W33, TBA!V14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!W39 | Construction\|39\|Construction!r2 | Y19 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*W33*TBA!V14 | Input Assumptions!D35, Input Assumptions!D36, Construction!W33, TBA!V14 |
| Construction!W43 | Construction\|43\|Construction!r2 | Y19 | same_period | W16-W28<0.01 | Construction!W16, Construction!W28 |
| Construction!W6 | Construction\|6\|Construction!r2 | Y19 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!V8 | Input Assumptions!D25, Input Assumptions!D9, TBA!V8 |
| Construction!W8 | Construction\|8\|Construction!r2 | Y19 | aggregation | SUM(W6:W7) | Construction!W6:W7 |
| Construction!X12 | Construction\|12\|Construction!r2 | Y20 | same_period | X8 | Construction!X8 |
| Construction!X13 | Construction\|13\|Construction!r2 | Y20 | same_period | X37 | Construction!X37 |
| Construction!X14 | Construction\|14\|Construction!r2 | Y20 | same_period | X38 | Construction!X38 |
| Construction!X15 | Construction\|15\|Construction!r2 | Y20 | same_period | X39 | Construction!X39 |
| Construction!X16 | Construction\|16\|Construction!r2 | Y20 | aggregation | SUM(X12:X15) | Construction!X12:X15 |
| Construction!X26 | Construction\|26\|Construction!r2 | Y20 | conditional | IF(MAX($C$22-SUM($D$26:W26),0)>X19,X19,MAX($C$22-SUM($D$26:W26),0)) | Construction!C22, Construction!D26:W26, Construction!X19 |
| Construction!X27 | Construction\|27\|Construction!r2 | Y20 | conditional | IF(X19-X26>0,X19-X26,0) | Construction!X19, Construction!X26 |
| Construction!X28 | Construction\|28\|Construction!r2 | Y20 | aggregation | SUM(X26:X27) | Construction!X26:X27 |
| Construction!X33 | Construction\|33\|Construction!r2 | Y20 | rollforward | W35 | Construction!W35 |
| Construction!X34 | Construction\|34\|Construction!r2 | Y20 | same_period | X27 | Construction!X27 |
| Construction!X35 | Construction\|35\|Construction!r2 | Y20 | aggregation | SUM(X33:X34) | Construction!X33:X34 |
| Construction!X37 | Construction\|37\|Construction!r2 | Y20 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!W13 | Input Assumptions!D37, Construction!C34, TBA!W13 |
| Construction!X38 | Construction\|38\|Construction!r2 | Y20 | same_period | ($C$34-X33)*TBA!W14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!X33, TBA!W14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!X39 | Construction\|39\|Construction!r2 | Y20 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*X33*TBA!W14 | Input Assumptions!D35, Input Assumptions!D36, Construction!X33, TBA!W14 |
| Construction!X43 | Construction\|43\|Construction!r2 | Y20 | same_period | X16-X28<0.01 | Construction!X16, Construction!X28 |
| Construction!X6 | Construction\|6\|Construction!r2 | Y20 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!W8 | Input Assumptions!D25, Input Assumptions!D9, TBA!W8 |
| Construction!X8 | Construction\|8\|Construction!r2 | Y20 | aggregation | SUM(X6:X7) | Construction!X6:X7 |
| Construction!Y12 | Construction\|12\|Construction!r2 | Y21 | same_period | Y8 | Construction!Y8 |
| Construction!Y13 | Construction\|13\|Construction!r2 | Y21 | same_period | Y37 | Construction!Y37 |
| Construction!Y14 | Construction\|14\|Construction!r2 | Y21 | same_period | Y38 | Construction!Y38 |
| Construction!Y15 | Construction\|15\|Construction!r2 | Y21 | same_period | Y39 | Construction!Y39 |
| Construction!Y16 | Construction\|16\|Construction!r2 | Y21 | aggregation | SUM(Y12:Y15) | Construction!Y12:Y15 |
| Construction!Y26 | Construction\|26\|Construction!r2 | Y21 | conditional | IF(MAX($C$22-SUM($D$26:X26),0)>Y19,Y19,MAX($C$22-SUM($D$26:X26),0)) | Construction!C22, Construction!D26:X26, Construction!Y19 |
| Construction!Y27 | Construction\|27\|Construction!r2 | Y21 | conditional | IF(Y19-Y26>0,Y19-Y26,0) | Construction!Y19, Construction!Y26 |
| Construction!Y28 | Construction\|28\|Construction!r2 | Y21 | aggregation | SUM(Y26:Y27) | Construction!Y26:Y27 |
| Construction!Y33 | Construction\|33\|Construction!r2 | Y21 | rollforward | X35 | Construction!X35 |
| Construction!Y34 | Construction\|34\|Construction!r2 | Y21 | same_period | Y27 | Construction!Y27 |
| Construction!Y35 | Construction\|35\|Construction!r2 | Y21 | aggregation | SUM(Y33:Y34) | Construction!Y33:Y34 |
| Construction!Y37 | Construction\|37\|Construction!r2 | Y21 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!X13 | Input Assumptions!D37, Construction!C34, TBA!X13 |
| Construction!Y38 | Construction\|38\|Construction!r2 | Y21 | same_period | ($C$34-Y33)*TBA!X14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!Y33, TBA!X14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!Y39 | Construction\|39\|Construction!r2 | Y21 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Y33*TBA!X14 | Input Assumptions!D35, Input Assumptions!D36, Construction!Y33, TBA!X14 |
| Construction!Y43 | Construction\|43\|Construction!r2 | Y21 | same_period | Y16-Y28<0.01 | Construction!Y16, Construction!Y28 |
| Construction!Y6 | Construction\|6\|Construction!r2 | Y21 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!X8 | Input Assumptions!D25, Input Assumptions!D9, TBA!X8 |
| Construction!Y8 | Construction\|8\|Construction!r2 | Y21 | aggregation | SUM(Y6:Y7) | Construction!Y6:Y7 |
| Construction!Z12 | Construction\|12\|Construction!r2 | Y22 | same_period | Z8 | Construction!Z8 |
| Construction!Z13 | Construction\|13\|Construction!r2 | Y22 | same_period | Z37 | Construction!Z37 |
| Construction!Z14 | Construction\|14\|Construction!r2 | Y22 | same_period | Z38 | Construction!Z38 |
| Construction!Z15 | Construction\|15\|Construction!r2 | Y22 | same_period | Z39 | Construction!Z39 |
| Construction!Z16 | Construction\|16\|Construction!r2 | Y22 | aggregation | SUM(Z12:Z15) | Construction!Z12:Z15 |
| Construction!Z26 | Construction\|26\|Construction!r2 | Y22 | conditional | IF(MAX($C$22-SUM($D$26:Y26),0)>Z19,Z19,MAX($C$22-SUM($D$26:Y26),0)) | Construction!C22, Construction!D26:Y26, Construction!Z19 |
| Construction!Z27 | Construction\|27\|Construction!r2 | Y22 | conditional | IF(Z19-Z26>0,Z19-Z26,0) | Construction!Z19, Construction!Z26 |
| Construction!Z28 | Construction\|28\|Construction!r2 | Y22 | aggregation | SUM(Z26:Z27) | Construction!Z26:Z27 |
| Construction!Z33 | Construction\|33\|Construction!r2 | Y22 | rollforward | Y35 | Construction!Y35 |
| Construction!Z34 | Construction\|34\|Construction!r2 | Y22 | same_period | Z27 | Construction!Z27 |
| Construction!Z35 | Construction\|35\|Construction!r2 | Y22 | aggregation | SUM(Z33:Z34) | Construction!Z33:Z34 |
| Construction!Z37 | Construction\|37\|Construction!r2 | Y22 | same_period | 'Input Assumptions'!$D$37*Construction!$C$34*TBA!Y13 | Input Assumptions!D37, Construction!C34, TBA!Y13 |
| Construction!Z38 | Construction\|38\|Construction!r2 | Y22 | same_period | ($C$34-Z33)*TBA!Y14*'Input Assumptions'!$D$36*'Input Assumptions'!$D$38 | Construction!C34, Construction!Z33, TBA!Y14, Input Assumptions!D36, Input Assumptions!D38 |
| Construction!Z39 | Construction\|39\|Construction!r2 | Y22 | same_period | ('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Z33*TBA!Y14 | Input Assumptions!D35, Input Assumptions!D36, Construction!Z33, TBA!Y14 |
| Construction!Z43 | Construction\|43\|Construction!r2 | Y22 | same_period | Z16-Z28<0.01 | Construction!Z16, Construction!Z28 |
| Construction!Z6 | Construction\|6\|Construction!r2 | Y22 | same_period | 'Input Assumptions'!$D$25/'Input Assumptions'!$D$9/1000*TBA!Y8 | Input Assumptions!D25, Input Assumptions!D9, TBA!Y8 |
| Construction!Z8 | Construction\|8\|Construction!r2 | Y22 | aggregation | SUM(Z6:Z7) | Construction!Z6:Z7 |
| Debt!AA10 | Debt\|10\|Debt!r3 | Y22 | conditional | IF(TBA!Y18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AA3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!Y18, Input Assumptions!D35, Input Assumptions!D36, Debt!AA3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AA11 | Debt\|11\|Debt!r3 | Y22 | aggregation | SUM(AA8:AA10) | Debt!AA8:AA10 |
| Debt!AA14 | Debt\|14\|Debt!r3 | Y22 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AA8*TBA!Y18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AA8, TBA!Y18 |
| Debt!AA17 | Debt\|17\|Debt!r3 | Y22 | same_period | (AA10+AA14)*TBA!Y18 | Debt!AA10, Debt!AA14, TBA!Y18 |
| Debt!AA8 | Debt\|8\|Debt!r3 | Y22 | rollforward | Z11 | Debt!Z11 |
| Debt!AA9 | Debt\|9\|Debt!r3 | Y22 | same_period | Construction!Z34 | Construction!Z34 |
| Debt!AB10 | Debt\|10\|Debt!r3 | Y23 | conditional | IF(TBA!Z18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AB3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!Z18, Input Assumptions!D35, Input Assumptions!D36, Debt!AB3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AB11 | Debt\|11\|Debt!r3 | Y23 | aggregation | SUM(AB8:AB10) | Debt!AB8:AB10 |
| Debt!AB14 | Debt\|14\|Debt!r3 | Y23 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AB8*TBA!Z18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AB8, TBA!Z18 |
| Debt!AB17 | Debt\|17\|Debt!r3 | Y23 | same_period | (AB10+AB14)*TBA!Z18 | Debt!AB10, Debt!AB14, TBA!Z18 |
| Debt!AB8 | Debt\|8\|Debt!r3 | Y23 | rollforward | AA11 | Debt!AA11 |
| Debt!AB9 | Debt\|9\|Debt!r3 | Y23 | same_period | Construction!AA34 | Construction!AA34 |
| Debt!AC10 | Debt\|10\|Debt!r3 | Y24 | conditional | IF(TBA!AA18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AC3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AA18, Input Assumptions!D35, Input Assumptions!D36, Debt!AC3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AC11 | Debt\|11\|Debt!r3 | Y24 | aggregation | SUM(AC8:AC10) | Debt!AC8:AC10 |
| Debt!AC14 | Debt\|14\|Debt!r3 | Y24 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AC8*TBA!AA18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AC8, TBA!AA18 |
| Debt!AC17 | Debt\|17\|Debt!r3 | Y24 | same_period | (AC10+AC14)*TBA!AA18 | Debt!AC10, Debt!AC14, TBA!AA18 |
| Debt!AC8 | Debt\|8\|Debt!r3 | Y24 | rollforward | AB11 | Debt!AB11 |
| Debt!AC9 | Debt\|9\|Debt!r3 | Y24 | same_period | Construction!AB34 | Construction!AB34 |
| Debt!AD10 | Debt\|10\|Debt!r3 | Y25 | conditional | IF(TBA!AB18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AD3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AB18, Input Assumptions!D35, Input Assumptions!D36, Debt!AD3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AD11 | Debt\|11\|Debt!r3 | Y25 | aggregation | SUM(AD8:AD10) | Debt!AD8:AD10 |
| Debt!AD14 | Debt\|14\|Debt!r3 | Y25 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AD8*TBA!AB18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AD8, TBA!AB18 |
| Debt!AD17 | Debt\|17\|Debt!r3 | Y25 | same_period | (AD10+AD14)*TBA!AB18 | Debt!AD10, Debt!AD14, TBA!AB18 |
| Debt!AD8 | Debt\|8\|Debt!r3 | Y25 | rollforward | AC11 | Debt!AC11 |
| Debt!AD9 | Debt\|9\|Debt!r3 | Y25 | same_period | Construction!AC34 | Construction!AC34 |
| Debt!AE10 | Debt\|10\|Debt!r3 | Y26 | conditional | IF(TBA!AC18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AE3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AC18, Input Assumptions!D35, Input Assumptions!D36, Debt!AE3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AE11 | Debt\|11\|Debt!r3 | Y26 | aggregation | SUM(AE8:AE10) | Debt!AE8:AE10 |
| Debt!AE14 | Debt\|14\|Debt!r3 | Y26 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AE8*TBA!AC18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AE8, TBA!AC18 |
| Debt!AE17 | Debt\|17\|Debt!r3 | Y26 | same_period | (AE10+AE14)*TBA!AC18 | Debt!AE10, Debt!AE14, TBA!AC18 |
| Debt!AE8 | Debt\|8\|Debt!r3 | Y26 | rollforward | AD11 | Debt!AD11 |
| Debt!AE9 | Debt\|9\|Debt!r3 | Y26 | same_period | Construction!AD34 | Construction!AD34 |
| Debt!AF10 | Debt\|10\|Debt!r3 | Y27 | conditional | IF(TBA!AD18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AF3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AD18, Input Assumptions!D35, Input Assumptions!D36, Debt!AF3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AF11 | Debt\|11\|Debt!r3 | Y27 | aggregation | SUM(AF8:AF10) | Debt!AF8:AF10 |
| Debt!AF14 | Debt\|14\|Debt!r3 | Y27 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AF8*TBA!AD18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AF8, TBA!AD18 |
| Debt!AF17 | Debt\|17\|Debt!r3 | Y27 | same_period | (AF10+AF14)*TBA!AD18 | Debt!AF10, Debt!AF14, TBA!AD18 |
| Debt!AF8 | Debt\|8\|Debt!r3 | Y27 | rollforward | AE11 | Debt!AE11 |
| Debt!AF9 | Debt\|9\|Debt!r3 | Y27 | same_period | Construction!AE34 | Construction!AE34 |
| Debt!AG10 | Debt\|10\|Debt!r3 | Y28 | conditional | IF(TBA!AE18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AG3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AE18, Input Assumptions!D35, Input Assumptions!D36, Debt!AG3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AG11 | Debt\|11\|Debt!r3 | Y28 | aggregation | SUM(AG8:AG10) | Debt!AG8:AG10 |
| Debt!AG14 | Debt\|14\|Debt!r3 | Y28 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AG8*TBA!AE18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AG8, TBA!AE18 |
| Debt!AG17 | Debt\|17\|Debt!r3 | Y28 | same_period | (AG10+AG14)*TBA!AE18 | Debt!AG10, Debt!AG14, TBA!AE18 |
| Debt!AG8 | Debt\|8\|Debt!r3 | Y28 | rollforward | AF11 | Debt!AF11 |
| Debt!AG9 | Debt\|9\|Debt!r3 | Y28 | same_period | Construction!AF34 | Construction!AF34 |
| Debt!AH10 | Debt\|10\|Debt!r3 | Y29 | conditional | IF(TBA!AF18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AH3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AF18, Input Assumptions!D35, Input Assumptions!D36, Debt!AH3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AH11 | Debt\|11\|Debt!r3 | Y29 | aggregation | SUM(AH8:AH10) | Debt!AH8:AH10 |
| Debt!AH14 | Debt\|14\|Debt!r3 | Y29 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AH8*TBA!AF18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AH8, TBA!AF18 |
| Debt!AH17 | Debt\|17\|Debt!r3 | Y29 | same_period | (AH10+AH14)*TBA!AF18 | Debt!AH10, Debt!AH14, TBA!AF18 |
| Debt!AH8 | Debt\|8\|Debt!r3 | Y29 | rollforward | AG11 | Debt!AG11 |
| Debt!AH9 | Debt\|9\|Debt!r3 | Y29 | same_period | Construction!AG34 | Construction!AG34 |
| Debt!AI10 | Debt\|10\|Debt!r3 | Y30 | conditional | IF(TBA!AG18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AI3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AG18, Input Assumptions!D35, Input Assumptions!D36, Debt!AI3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AI11 | Debt\|11\|Debt!r3 | Y30 | aggregation | SUM(AI8:AI10) | Debt!AI8:AI10 |
| Debt!AI14 | Debt\|14\|Debt!r3 | Y30 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AI8*TBA!AG18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AI8, TBA!AG18 |
| Debt!AI17 | Debt\|17\|Debt!r3 | Y30 | same_period | (AI10+AI14)*TBA!AG18 | Debt!AI10, Debt!AI14, TBA!AG18 |
| Debt!AI8 | Debt\|8\|Debt!r3 | Y30 | rollforward | AH11 | Debt!AH11 |
| Debt!AI9 | Debt\|9\|Debt!r3 | Y30 | same_period | Construction!AH34 | Construction!AH34 |
| Debt!AJ10 | Debt\|10\|Debt!r3 | Y31 | conditional | IF(TBA!AH18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AJ3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AH18, Input Assumptions!D35, Input Assumptions!D36, Debt!AJ3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AJ11 | Debt\|11\|Debt!r3 | Y31 | aggregation | SUM(AJ8:AJ10) | Debt!AJ8:AJ10 |
| Debt!AJ14 | Debt\|14\|Debt!r3 | Y31 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AJ8*TBA!AH18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AJ8, TBA!AH18 |
| Debt!AJ17 | Debt\|17\|Debt!r3 | Y31 | same_period | (AJ10+AJ14)*TBA!AH18 | Debt!AJ10, Debt!AJ14, TBA!AH18 |
| Debt!AJ8 | Debt\|8\|Debt!r3 | Y31 | rollforward | AI11 | Debt!AI11 |
| Debt!AJ9 | Debt\|9\|Debt!r3 | Y31 | same_period | Construction!AI34 | Construction!AI34 |
| Debt!AK10 | Debt\|10\|Debt!r3 | Y32 | conditional | IF(TBA!AI18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AK3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AI18, Input Assumptions!D35, Input Assumptions!D36, Debt!AK3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AK11 | Debt\|11\|Debt!r3 | Y32 | aggregation | SUM(AK8:AK10) | Debt!AK8:AK10 |
| Debt!AK14 | Debt\|14\|Debt!r3 | Y32 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AK8*TBA!AI18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AK8, TBA!AI18 |
| Debt!AK17 | Debt\|17\|Debt!r3 | Y32 | same_period | (AK10+AK14)*TBA!AI18 | Debt!AK10, Debt!AK14, TBA!AI18 |
| Debt!AK8 | Debt\|8\|Debt!r3 | Y32 | rollforward | AJ11 | Debt!AJ11 |
| Debt!AK9 | Debt\|9\|Debt!r3 | Y32 | same_period | Construction!AJ34 | Construction!AJ34 |
| Debt!AL10 | Debt\|10\|Debt!r3 | Y33 | conditional | IF(TBA!AJ18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AL3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AJ18, Input Assumptions!D35, Input Assumptions!D36, Debt!AL3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AL11 | Debt\|11\|Debt!r3 | Y33 | aggregation | SUM(AL8:AL10) | Debt!AL8:AL10 |
| Debt!AL14 | Debt\|14\|Debt!r3 | Y33 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AL8*TBA!AJ18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AL8, TBA!AJ18 |
| Debt!AL17 | Debt\|17\|Debt!r3 | Y33 | same_period | (AL10+AL14)*TBA!AJ18 | Debt!AL10, Debt!AL14, TBA!AJ18 |
| Debt!AL8 | Debt\|8\|Debt!r3 | Y33 | rollforward | AK11 | Debt!AK11 |
| Debt!AL9 | Debt\|9\|Debt!r3 | Y33 | same_period | Construction!AK34 | Construction!AK34 |
| Debt!AM10 | Debt\|10\|Debt!r3 | Y34 | conditional | IF(TBA!AK18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AM3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AK18, Input Assumptions!D35, Input Assumptions!D36, Debt!AM3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AM11 | Debt\|11\|Debt!r3 | Y34 | aggregation | SUM(AM8:AM10) | Debt!AM8:AM10 |
| Debt!AM14 | Debt\|14\|Debt!r3 | Y34 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AM8*TBA!AK18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AM8, TBA!AK18 |
| Debt!AM17 | Debt\|17\|Debt!r3 | Y34 | same_period | (AM10+AM14)*TBA!AK18 | Debt!AM10, Debt!AM14, TBA!AK18 |
| Debt!AM8 | Debt\|8\|Debt!r3 | Y34 | rollforward | AL11 | Debt!AL11 |
| Debt!AM9 | Debt\|9\|Debt!r3 | Y34 | same_period | Construction!AL34 | Construction!AL34 |
| Debt!AN10 | Debt\|10\|Debt!r3 | Y35 | conditional | IF(TBA!AL18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AN3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AL18, Input Assumptions!D35, Input Assumptions!D36, Debt!AN3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AN11 | Debt\|11\|Debt!r3 | Y35 | aggregation | SUM(AN8:AN10) | Debt!AN8:AN10 |
| Debt!AN14 | Debt\|14\|Debt!r3 | Y35 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AN8*TBA!AL18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AN8, TBA!AL18 |
| Debt!AN17 | Debt\|17\|Debt!r3 | Y35 | same_period | (AN10+AN14)*TBA!AL18 | Debt!AN10, Debt!AN14, TBA!AL18 |
| Debt!AN8 | Debt\|8\|Debt!r3 | Y35 | rollforward | AM11 | Debt!AM11 |
| Debt!AN9 | Debt\|9\|Debt!r3 | Y35 | same_period | Construction!AM34 | Construction!AM34 |
| Debt!AO10 | Debt\|10\|Debt!r3 | Y36 | conditional | IF(TBA!AM18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AO3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AM18, Input Assumptions!D35, Input Assumptions!D36, Debt!AO3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AO11 | Debt\|11\|Debt!r3 | Y36 | aggregation | SUM(AO8:AO10) | Debt!AO8:AO10 |
| Debt!AO14 | Debt\|14\|Debt!r3 | Y36 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AO8*TBA!AM18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AO8, TBA!AM18 |
| Debt!AO17 | Debt\|17\|Debt!r3 | Y36 | same_period | (AO10+AO14)*TBA!AM18 | Debt!AO10, Debt!AO14, TBA!AM18 |
| Debt!AO8 | Debt\|8\|Debt!r3 | Y36 | rollforward | AN11 | Debt!AN11 |
| Debt!AO9 | Debt\|9\|Debt!r3 | Y36 | same_period | Construction!AN34 | Construction!AN34 |
| Debt!AP10 | Debt\|10\|Debt!r3 | Y37 | conditional | IF(TBA!AN18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AP3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AN18, Input Assumptions!D35, Input Assumptions!D36, Debt!AP3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AP11 | Debt\|11\|Debt!r3 | Y37 | aggregation | SUM(AP8:AP10) | Debt!AP8:AP10 |
| Debt!AP14 | Debt\|14\|Debt!r3 | Y37 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AP8*TBA!AN18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AP8, TBA!AN18 |
| Debt!AP17 | Debt\|17\|Debt!r3 | Y37 | same_period | (AP10+AP14)*TBA!AN18 | Debt!AP10, Debt!AP14, TBA!AN18 |
| Debt!AP8 | Debt\|8\|Debt!r3 | Y37 | rollforward | AO11 | Debt!AO11 |
| Debt!AP9 | Debt\|9\|Debt!r3 | Y37 | same_period | Construction!AO34 | Construction!AO34 |
| Debt!AQ10 | Debt\|10\|Debt!r3 | Y38 | conditional | IF(TBA!AO18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AQ3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AO18, Input Assumptions!D35, Input Assumptions!D36, Debt!AQ3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AQ11 | Debt\|11\|Debt!r3 | Y38 | aggregation | SUM(AQ8:AQ10) | Debt!AQ8:AQ10 |
| Debt!AQ14 | Debt\|14\|Debt!r3 | Y38 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AQ8*TBA!AO18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AQ8, TBA!AO18 |
| Debt!AQ17 | Debt\|17\|Debt!r3 | Y38 | same_period | (AQ10+AQ14)*TBA!AO18 | Debt!AQ10, Debt!AQ14, TBA!AO18 |
| Debt!AQ8 | Debt\|8\|Debt!r3 | Y38 | rollforward | AP11 | Debt!AP11 |
| Debt!AQ9 | Debt\|9\|Debt!r3 | Y38 | same_period | Construction!AP34 | Construction!AP34 |
| Debt!AR10 | Debt\|10\|Debt!r3 | Y39 | conditional | IF(TBA!AP18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AR3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AP18, Input Assumptions!D35, Input Assumptions!D36, Debt!AR3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AR11 | Debt\|11\|Debt!r3 | Y39 | aggregation | SUM(AR8:AR10) | Debt!AR8:AR10 |
| Debt!AR14 | Debt\|14\|Debt!r3 | Y39 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AR8*TBA!AP18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AR8, TBA!AP18 |
| Debt!AR17 | Debt\|17\|Debt!r3 | Y39 | same_period | (AR10+AR14)*TBA!AP18 | Debt!AR10, Debt!AR14, TBA!AP18 |
| Debt!AR8 | Debt\|8\|Debt!r3 | Y39 | rollforward | AQ11 | Debt!AQ11 |
| Debt!AR9 | Debt\|9\|Debt!r3 | Y39 | same_period | Construction!AQ34 | Construction!AQ34 |
| Debt!AS10 | Debt\|10\|Debt!r3 | Y40 | conditional | IF(TBA!AQ18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!AS3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!AQ18, Input Assumptions!D35, Input Assumptions!D36, Debt!AS3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!AS11 | Debt\|11\|Debt!r3 | Y40 | aggregation | SUM(AS8:AS10) | Debt!AS8:AS10 |
| Debt!AS14 | Debt\|14\|Debt!r3 | Y40 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!AS8*TBA!AQ18 | Input Assumptions!D35, Input Assumptions!D36, Debt!AS8, TBA!AQ18 |
| Debt!AS17 | Debt\|17\|Debt!r3 | Y40 | same_period | (AS10+AS14)*TBA!AQ18 | Debt!AS10, Debt!AS14, TBA!AQ18 |
| Debt!AS8 | Debt\|8\|Debt!r3 | Y40 | rollforward | AR11 | Debt!AR11 |
| Debt!AS9 | Debt\|9\|Debt!r3 | Y40 | same_period | Construction!AR34 | Construction!AR34 |
| Debt!F10 | Debt\|10\|Debt!r3 | Y1 | conditional | IF(TBA!D18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!F3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!D18, Input Assumptions!D35, Input Assumptions!D36, Debt!F3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!F11 | Debt\|11\|Debt!r3 | Y1 | aggregation | SUM(F8:F10) | Debt!F8:F10 |
| Debt!F14 | Debt\|14\|Debt!r3 | Y1 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!F8*TBA!D18 | Input Assumptions!D35, Input Assumptions!D36, Debt!F8, TBA!D18 |
| Debt!F17 | Debt\|17\|Debt!r3 | Y1 | same_period | (F10+F14)*TBA!D18 | Debt!F10, Debt!F14, TBA!D18 |
| Debt!F8 | Debt\|8\|Debt!r3 | Y1 | same_period | E11 | Debt!E11 |
| Debt!F9 | Debt\|9\|Debt!r3 | Y1 | same_period | Construction!E34 | Construction!E34 |
| Debt!G10 | Debt\|10\|Debt!r3 | Y2 | conditional | IF(TBA!E18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!G3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!E18, Input Assumptions!D35, Input Assumptions!D36, Debt!G3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!G11 | Debt\|11\|Debt!r3 | Y2 | aggregation | SUM(G8:G10) | Debt!G8:G10 |
| Debt!G14 | Debt\|14\|Debt!r3 | Y2 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!G8*TBA!E18 | Input Assumptions!D35, Input Assumptions!D36, Debt!G8, TBA!E18 |
| Debt!G17 | Debt\|17\|Debt!r3 | Y2 | same_period | (G10+G14)*TBA!E18 | Debt!G10, Debt!G14, TBA!E18 |
| Debt!G8 | Debt\|8\|Debt!r3 | Y2 | rollforward | F11 | Debt!F11 |
| Debt!G9 | Debt\|9\|Debt!r3 | Y2 | same_period | Construction!F34 | Construction!F34 |
| Debt!H10 | Debt\|10\|Debt!r3 | Y3 | conditional | IF(TBA!F18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!H3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!F18, Input Assumptions!D35, Input Assumptions!D36, Debt!H3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!H11 | Debt\|11\|Debt!r3 | Y3 | aggregation | SUM(H8:H10) | Debt!H8:H10 |
| Debt!H14 | Debt\|14\|Debt!r3 | Y3 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!H8*TBA!F18 | Input Assumptions!D35, Input Assumptions!D36, Debt!H8, TBA!F18 |
| Debt!H17 | Debt\|17\|Debt!r3 | Y3 | same_period | (H10+H14)*TBA!F18 | Debt!H10, Debt!H14, TBA!F18 |
| Debt!H8 | Debt\|8\|Debt!r3 | Y3 | rollforward | G11 | Debt!G11 |
| Debt!H9 | Debt\|9\|Debt!r3 | Y3 | same_period | Construction!G34 | Construction!G34 |
| Debt!I10 | Debt\|10\|Debt!r3 | Y4 | conditional | IF(TBA!G18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!I3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!G18, Input Assumptions!D35, Input Assumptions!D36, Debt!I3, TBA!C18, Construction!C34 |
| Debt!I11 | Debt\|11\|Debt!r3 | Y4 | aggregation | SUM(I8:I10) | Debt!I8:I10 |
| Debt!I14 | Debt\|14\|Debt!r3 | Y4 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!I8*TBA!G18 | Input Assumptions!D35, Input Assumptions!D36, Debt!I8, TBA!G18 |
| Debt!I17 | Debt\|17\|Debt!r3 | Y4 | same_period | (I10+I14)*TBA!G18 | Debt!I10, Debt!I14, TBA!G18 |
| Debt!I8 | Debt\|8\|Debt!r3 | Y4 | rollforward | H11 | Debt!H11 |
| Debt!I9 | Debt\|9\|Debt!r3 | Y4 | same_period | Construction!H34 | Construction!H34 |
| Debt!J10 | Debt\|10\|Debt!r3 | Y5 | conditional | IF(TBA!H18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!J3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!H18, Input Assumptions!D35, Input Assumptions!D36, Debt!J3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!J11 | Debt\|11\|Debt!r3 | Y5 | aggregation | SUM(J8:J10) | Debt!J8:J10 |
| Debt!J14 | Debt\|14\|Debt!r3 | Y5 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!J8*TBA!H18 | Input Assumptions!D35, Input Assumptions!D36, Debt!J8, TBA!H18 |
| Debt!J17 | Debt\|17\|Debt!r3 | Y5 | same_period | (J10+J14)*TBA!H18 | Debt!J10, Debt!J14, TBA!H18 |
| Debt!J8 | Debt\|8\|Debt!r3 | Y5 | rollforward | I11 | Debt!I11 |
| Debt!J9 | Debt\|9\|Debt!r3 | Y5 | same_period | Construction!I34 | Construction!I34 |
| Debt!K10 | Debt\|10\|Debt!r3 | Y6 | conditional | IF(TBA!I18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!K3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!I18, Input Assumptions!D35, Input Assumptions!D36, Debt!K3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!K11 | Debt\|11\|Debt!r3 | Y6 | aggregation | SUM(K8:K10) | Debt!K8:K10 |
| Debt!K14 | Debt\|14\|Debt!r3 | Y6 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!K8*TBA!I18 | Input Assumptions!D35, Input Assumptions!D36, Debt!K8, TBA!I18 |
| Debt!K17 | Debt\|17\|Debt!r3 | Y6 | same_period | (K10+K14)*TBA!I18 | Debt!K10, Debt!K14, TBA!I18 |
| Debt!K8 | Debt\|8\|Debt!r3 | Y6 | rollforward | J11 | Debt!J11 |
| Debt!K9 | Debt\|9\|Debt!r3 | Y6 | same_period | Construction!J34 | Construction!J34 |
| Debt!L10 | Debt\|10\|Debt!r3 | Y7 | conditional | IF(TBA!J18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!L3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!J18, Input Assumptions!D35, Input Assumptions!D36, Debt!L3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!L11 | Debt\|11\|Debt!r3 | Y7 | aggregation | SUM(L8:L10) | Debt!L8:L10 |
| Debt!L14 | Debt\|14\|Debt!r3 | Y7 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!L8*TBA!J18 | Input Assumptions!D35, Input Assumptions!D36, Debt!L8, TBA!J18 |
| Debt!L17 | Debt\|17\|Debt!r3 | Y7 | same_period | (L10+L14)*TBA!J18 | Debt!L10, Debt!L14, TBA!J18 |
| Debt!L8 | Debt\|8\|Debt!r3 | Y7 | rollforward | K11 | Debt!K11 |
| Debt!L9 | Debt\|9\|Debt!r3 | Y7 | same_period | Construction!K34 | Construction!K34 |
| Debt!M10 | Debt\|10\|Debt!r3 | Y8 | conditional | IF(TBA!K18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!M3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!K18, Input Assumptions!D35, Input Assumptions!D36, Debt!M3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!M11 | Debt\|11\|Debt!r3 | Y8 | aggregation | SUM(M8:M10) | Debt!M8:M10 |
| Debt!M14 | Debt\|14\|Debt!r3 | Y8 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!M8*TBA!K18 | Input Assumptions!D35, Input Assumptions!D36, Debt!M8, TBA!K18 |
| Debt!M17 | Debt\|17\|Debt!r3 | Y8 | same_period | (M10+M14)*TBA!K18 | Debt!M10, Debt!M14, TBA!K18 |
| Debt!M8 | Debt\|8\|Debt!r3 | Y8 | rollforward | L11 | Debt!L11 |
| Debt!M9 | Debt\|9\|Debt!r3 | Y8 | same_period | Construction!L34 | Construction!L34 |
| Debt!N10 | Debt\|10\|Debt!r3 | Y9 | conditional | IF(TBA!L18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!N3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!L18, Input Assumptions!D35, Input Assumptions!D36, Debt!N3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!N11 | Debt\|11\|Debt!r3 | Y9 | aggregation | SUM(N8:N10) | Debt!N8:N10 |
| Debt!N14 | Debt\|14\|Debt!r3 | Y9 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!N8*TBA!L18 | Input Assumptions!D35, Input Assumptions!D36, Debt!N8, TBA!L18 |
| Debt!N17 | Debt\|17\|Debt!r3 | Y9 | same_period | (N10+N14)*TBA!L18 | Debt!N10, Debt!N14, TBA!L18 |
| Debt!N8 | Debt\|8\|Debt!r3 | Y9 | rollforward | M11 | Debt!M11 |
| Debt!N9 | Debt\|9\|Debt!r3 | Y9 | same_period | Construction!M34 | Construction!M34 |
| Debt!O10 | Debt\|10\|Debt!r3 | Y10 | conditional | IF(TBA!M18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!O3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!M18, Input Assumptions!D35, Input Assumptions!D36, Debt!O3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!O11 | Debt\|11\|Debt!r3 | Y10 | aggregation | SUM(O8:O10) | Debt!O8:O10 |
| Debt!O14 | Debt\|14\|Debt!r3 | Y10 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!O8*TBA!M18 | Input Assumptions!D35, Input Assumptions!D36, Debt!O8, TBA!M18 |
| Debt!O17 | Debt\|17\|Debt!r3 | Y10 | same_period | (O10+O14)*TBA!M18 | Debt!O10, Debt!O14, TBA!M18 |
| Debt!O8 | Debt\|8\|Debt!r3 | Y10 | rollforward | N11 | Debt!N11 |
| Debt!O9 | Debt\|9\|Debt!r3 | Y10 | same_period | Construction!N34 | Construction!N34 |
| Debt!P10 | Debt\|10\|Debt!r3 | Y11 | conditional | IF(TBA!N18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!P3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!N18, Input Assumptions!D35, Input Assumptions!D36, Debt!P3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!P11 | Debt\|11\|Debt!r3 | Y11 | aggregation | SUM(P8:P10) | Debt!P8:P10 |
| Debt!P14 | Debt\|14\|Debt!r3 | Y11 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!P8*TBA!N18 | Input Assumptions!D35, Input Assumptions!D36, Debt!P8, TBA!N18 |
| Debt!P17 | Debt\|17\|Debt!r3 | Y11 | same_period | (P10+P14)*TBA!N18 | Debt!P10, Debt!P14, TBA!N18 |
| Debt!P8 | Debt\|8\|Debt!r3 | Y11 | rollforward | O11 | Debt!O11 |
| Debt!P9 | Debt\|9\|Debt!r3 | Y11 | same_period | Construction!O34 | Construction!O34 |
| Debt!Q10 | Debt\|10\|Debt!r3 | Y12 | conditional | IF(TBA!O18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!Q3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!O18, Input Assumptions!D35, Input Assumptions!D36, Debt!Q3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!Q11 | Debt\|11\|Debt!r3 | Y12 | aggregation | SUM(Q8:Q10) | Debt!Q8:Q10 |
| Debt!Q14 | Debt\|14\|Debt!r3 | Y12 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!Q8*TBA!O18 | Input Assumptions!D35, Input Assumptions!D36, Debt!Q8, TBA!O18 |
| Debt!Q17 | Debt\|17\|Debt!r3 | Y12 | same_period | (Q10+Q14)*TBA!O18 | Debt!Q10, Debt!Q14, TBA!O18 |
| Debt!Q8 | Debt\|8\|Debt!r3 | Y12 | rollforward | P11 | Debt!P11 |
| Debt!Q9 | Debt\|9\|Debt!r3 | Y12 | same_period | Construction!P34 | Construction!P34 |
| Debt!R10 | Debt\|10\|Debt!r3 | Y13 | conditional | IF(TBA!P18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!R3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!P18, Input Assumptions!D35, Input Assumptions!D36, Debt!R3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!R11 | Debt\|11\|Debt!r3 | Y13 | aggregation | SUM(R8:R10) | Debt!R8:R10 |
| Debt!R14 | Debt\|14\|Debt!r3 | Y13 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!R8*TBA!P18 | Input Assumptions!D35, Input Assumptions!D36, Debt!R8, TBA!P18 |
| Debt!R17 | Debt\|17\|Debt!r3 | Y13 | same_period | (R10+R14)*TBA!P18 | Debt!R10, Debt!R14, TBA!P18 |
| Debt!R8 | Debt\|8\|Debt!r3 | Y13 | rollforward | Q11 | Debt!Q11 |
| Debt!R9 | Debt\|9\|Debt!r3 | Y13 | same_period | Construction!Q34 | Construction!Q34 |
| Debt!S10 | Debt\|10\|Debt!r3 | Y14 | conditional | IF(TBA!Q18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!S3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!Q18, Input Assumptions!D35, Input Assumptions!D36, Debt!S3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!S11 | Debt\|11\|Debt!r3 | Y14 | aggregation | SUM(S8:S10) | Debt!S8:S10 |
| Debt!S14 | Debt\|14\|Debt!r3 | Y14 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!S8*TBA!Q18 | Input Assumptions!D35, Input Assumptions!D36, Debt!S8, TBA!Q18 |
| Debt!S17 | Debt\|17\|Debt!r3 | Y14 | same_period | (S10+S14)*TBA!Q18 | Debt!S10, Debt!S14, TBA!Q18 |
| Debt!S8 | Debt\|8\|Debt!r3 | Y14 | rollforward | R11 | Debt!R11 |
| Debt!S9 | Debt\|9\|Debt!r3 | Y14 | same_period | Construction!R34 | Construction!R34 |
| Debt!T10 | Debt\|10\|Debt!r3 | Y15 | conditional | IF(TBA!R18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!T3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!R18, Input Assumptions!D35, Input Assumptions!D36, Debt!T3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!T11 | Debt\|11\|Debt!r3 | Y15 | aggregation | SUM(T8:T10) | Debt!T8:T10 |
| Debt!T14 | Debt\|14\|Debt!r3 | Y15 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!T8*TBA!R18 | Input Assumptions!D35, Input Assumptions!D36, Debt!T8, TBA!R18 |
| Debt!T17 | Debt\|17\|Debt!r3 | Y15 | same_period | (T10+T14)*TBA!R18 | Debt!T10, Debt!T14, TBA!R18 |
| Debt!T8 | Debt\|8\|Debt!r3 | Y15 | rollforward | S11 | Debt!S11 |
| Debt!T9 | Debt\|9\|Debt!r3 | Y15 | same_period | Construction!S34 | Construction!S34 |
| Debt!U10 | Debt\|10\|Debt!r3 | Y16 | conditional | IF(TBA!S18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!U3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!S18, Input Assumptions!D35, Input Assumptions!D36, Debt!U3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!U11 | Debt\|11\|Debt!r3 | Y16 | aggregation | SUM(U8:U10) | Debt!U8:U10 |
| Debt!U14 | Debt\|14\|Debt!r3 | Y16 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!U8*TBA!S18 | Input Assumptions!D35, Input Assumptions!D36, Debt!U8, TBA!S18 |
| Debt!U17 | Debt\|17\|Debt!r3 | Y16 | same_period | (U10+U14)*TBA!S18 | Debt!U10, Debt!U14, TBA!S18 |
| Debt!U8 | Debt\|8\|Debt!r3 | Y16 | rollforward | T11 | Debt!T11 |
| Debt!U9 | Debt\|9\|Debt!r3 | Y16 | same_period | Construction!T34 | Construction!T34 |
| Debt!V10 | Debt\|10\|Debt!r3 | Y17 | conditional | IF(TBA!T18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!V3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!T18, Input Assumptions!D35, Input Assumptions!D36, Debt!V3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!V11 | Debt\|11\|Debt!r3 | Y17 | aggregation | SUM(V8:V10) | Debt!V8:V10 |
| Debt!V14 | Debt\|14\|Debt!r3 | Y17 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!V8*TBA!T18 | Input Assumptions!D35, Input Assumptions!D36, Debt!V8, TBA!T18 |
| Debt!V17 | Debt\|17\|Debt!r3 | Y17 | same_period | (V10+V14)*TBA!T18 | Debt!V10, Debt!V14, TBA!T18 |
| Debt!V8 | Debt\|8\|Debt!r3 | Y17 | rollforward | U11 | Debt!U11 |
| Debt!V9 | Debt\|9\|Debt!r3 | Y17 | same_period | Construction!U34 | Construction!U34 |
| Debt!W10 | Debt\|10\|Debt!r3 | Y18 | conditional | IF(TBA!U18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!W3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!U18, Input Assumptions!D35, Input Assumptions!D36, Debt!W3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!W11 | Debt\|11\|Debt!r3 | Y18 | aggregation | SUM(W8:W10) | Debt!W8:W10 |
| Debt!W14 | Debt\|14\|Debt!r3 | Y18 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!W8*TBA!U18 | Input Assumptions!D35, Input Assumptions!D36, Debt!W8, TBA!U18 |
| Debt!W17 | Debt\|17\|Debt!r3 | Y18 | same_period | (W10+W14)*TBA!U18 | Debt!W10, Debt!W14, TBA!U18 |
| Debt!W8 | Debt\|8\|Debt!r3 | Y18 | rollforward | V11 | Debt!V11 |
| Debt!W9 | Debt\|9\|Debt!r3 | Y18 | same_period | Construction!V34 | Construction!V34 |
| Debt!X10 | Debt\|10\|Debt!r3 | Y19 | conditional | IF(TBA!V18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!X3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!V18, Input Assumptions!D35, Input Assumptions!D36, Debt!X3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!X11 | Debt\|11\|Debt!r3 | Y19 | aggregation | SUM(X8:X10) | Debt!X8:X10 |
| Debt!X14 | Debt\|14\|Debt!r3 | Y19 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!X8*TBA!V18 | Input Assumptions!D35, Input Assumptions!D36, Debt!X8, TBA!V18 |
| Debt!X17 | Debt\|17\|Debt!r3 | Y19 | same_period | (X10+X14)*TBA!V18 | Debt!X10, Debt!X14, TBA!V18 |
| Debt!X8 | Debt\|8\|Debt!r3 | Y19 | rollforward | W11 | Debt!W11 |
| Debt!X9 | Debt\|9\|Debt!r3 | Y19 | same_period | Construction!W34 | Construction!W34 |
| Debt!Y10 | Debt\|10\|Debt!r3 | Y20 | conditional | IF(TBA!W18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!Y3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!W18, Input Assumptions!D35, Input Assumptions!D36, Debt!Y3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!Y11 | Debt\|11\|Debt!r3 | Y20 | aggregation | SUM(Y8:Y10) | Debt!Y8:Y10 |
| Debt!Y14 | Debt\|14\|Debt!r3 | Y20 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!Y8*TBA!W18 | Input Assumptions!D35, Input Assumptions!D36, Debt!Y8, TBA!W18 |
| Debt!Y17 | Debt\|17\|Debt!r3 | Y20 | same_period | (Y10+Y14)*TBA!W18 | Debt!Y10, Debt!Y14, TBA!W18 |
| Debt!Y8 | Debt\|8\|Debt!r3 | Y20 | rollforward | X11 | Debt!X11 |
| Debt!Y9 | Debt\|9\|Debt!r3 | Y20 | same_period | Construction!X34 | Construction!X34 |
| Debt!Z10 | Debt\|10\|Debt!r3 | Y21 | conditional | IF(TBA!X18=1,PPMT('Input Assumptions'!$D$35+'Input Assumptions'!$D$36,Debt!Z3-Debt!$I$3,TBA!$C$18,Construction!$C$34),0) | TBA!X18, Input Assumptions!D35, Input Assumptions!D36, Debt!Z3, Debt!I3, TBA!C18, Construction!C34 |
| Debt!Z11 | Debt\|11\|Debt!r3 | Y21 | aggregation | SUM(Z8:Z10) | Debt!Z8:Z10 |
| Debt!Z14 | Debt\|14\|Debt!r3 | Y21 | same_period | -('Input Assumptions'!$D$35+'Input Assumptions'!$D$36)*Debt!Z8*TBA!X18 | Input Assumptions!D35, Input Assumptions!D36, Debt!Z8, TBA!X18 |
| Debt!Z17 | Debt\|17\|Debt!r3 | Y21 | same_period | (Z10+Z14)*TBA!X18 | Debt!Z10, Debt!Z14, TBA!X18 |
| Debt!Z8 | Debt\|8\|Debt!r3 | Y21 | rollforward | Y11 | Debt!Y11 |
| Debt!Z9 | Debt\|9\|Debt!r3 | Y21 | same_period | Construction!Y34 | Construction!Y34 |
| Input Assumptions!D10 | Input Assumptions\|10\|Input Assumptions!r5 | value | same_period | INDEX(F10:O10,$D$3) | Input Assumptions!F10:O10, Input Assumptions!D3 |
| Input Assumptions!D14 | Input Assumptions\|14\|Input Assumptions!r5 | value | same_period | INDEX(F14:O14,$D$3) | Input Assumptions!F14:O14, Input Assumptions!D3 |
| Input Assumptions!D15 | Input Assumptions\|15\|Input Assumptions!r5 | value | same_period | INDEX(F15:O15,$D$3) | Input Assumptions!F15:O15, Input Assumptions!D3 |
| Input Assumptions!D17 | Input Assumptions\|17\|Input Assumptions!r5 | value | same_period | INDEX(F17:O17,$D$3) | Input Assumptions!F17:O17, Input Assumptions!D3 |
| Input Assumptions!D18 | Input Assumptions\|18\|Input Assumptions!r5 | value | same_period | INDEX(F18:O18,$D$3) | Input Assumptions!F18:O18, Input Assumptions!D3 |
| Input Assumptions!D20 | Input Assumptions\|20\|Input Assumptions!r5 | value | same_period | INDEX(F20:O20,$D$3) | Input Assumptions!F20:O20, Input Assumptions!D3 |
| Input Assumptions!D21 | Input Assumptions\|21\|Input Assumptions!r5 | value | same_period | INDEX(F21:O21,$D$3) | Input Assumptions!F21:O21, Input Assumptions!D3 |
| Input Assumptions!D25 | Input Assumptions\|25\|Input Assumptions!r5 | value | same_period | INDEX(F25:O25,$D$3) | Input Assumptions!F25:O25, Input Assumptions!D3 |
| Input Assumptions!D29 | Input Assumptions\|29\|Input Assumptions!r5 | value | same_period | INDEX(F29:O29,$D$3) | Input Assumptions!F29:O29, Input Assumptions!D3 |
| Input Assumptions!D31 | Input Assumptions\|31\|Input Assumptions!r5 | value | same_period | INDEX(F31:O31,$D$3) | Input Assumptions!F31:O31, Input Assumptions!D3 |
| Input Assumptions!D35 | Input Assumptions\|35\|Input Assumptions!r5 | value | same_period | INDEX(F35:O35,$D$3) | Input Assumptions!F35:O35, Input Assumptions!D3 |
| Input Assumptions!D36 | Input Assumptions\|36\|Input Assumptions!r5 | value | same_period | INDEX(F36:O36,$D$3) | Input Assumptions!F36:O36, Input Assumptions!D3 |
| Input Assumptions!D37 | Input Assumptions\|37\|Input Assumptions!r5 | value | same_period | INDEX(F37:O37,$D$3) | Input Assumptions!F37:O37, Input Assumptions!D3 |
| Input Assumptions!D38 | Input Assumptions\|38\|Input Assumptions!r5 | value | same_period | INDEX(F38:O38,$D$3) | Input Assumptions!F38:O38, Input Assumptions!D3 |
| Input Assumptions!D40 | Input Assumptions\|40\|Input Assumptions!r5 | value | same_period | INDEX(F40:O40,$D$3) | Input Assumptions!F40:O40, Input Assumptions!D3 |
| Input Assumptions!D44 | Input Assumptions\|44\|Input Assumptions!r5 | value | same_period | INDEX(F44:O44,$D$3) | Input Assumptions!F44:O44, Input Assumptions!D3 |
| Input Assumptions!D45 | Input Assumptions\|45\|Input Assumptions!r5 | value | same_period | INDEX(F45:O45,$D$3) | Input Assumptions!F45:O45, Input Assumptions!D3 |
| Input Assumptions!D8 | Input Assumptions\|8\|Input Assumptions!r5 | value | same_period | INDEX(F8:O8,$D$3) | Input Assumptions!F8:O8, Input Assumptions!D3 |
| Input Assumptions!D9 | Input Assumptions\|9\|Input Assumptions!r5 | value | same_period | INDEX(F9:O9,$D$3) | Input Assumptions!F9:O9, Input Assumptions!D3 |
| Operation!AA10 | Operation\|10\|Operation!r2 | Y23 | same_period | AA7*'Input Assumptions'!$D$20/1000 | Operation!AA7, Input Assumptions!D20 |
| Operation!AA11 | Operation\|11\|Operation!r2 | Y23 | same_period | AA8*'Input Assumptions'!$D$21/1000 | Operation!AA8, Input Assumptions!D21 |
| Operation!AA12 | Operation\|12\|Operation!r2 | Y23 | aggregation | SUM(AA10:AA11) | Operation!AA10:AA11 |
| Operation!AA14 | Operation\|14\|Operation!r2 | Y23 | cross_period | AA12*(1+'Input Assumptions'!$D$18)^(AA2-$E$2) | Operation!AA12, Input Assumptions!D18, Operation!AA2, Operation!E2 |
| Operation!AA20 | Operation\|20\|Operation!r2 | Y23 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AA2-$E$2)*TBA!Z10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AA2, Operation!E2, TBA!Z10 |
| Operation!AA21 | Operation\|21\|Operation!r2 | Y23 | aggregation | SUM(AA19:AA20) | Operation!AA19:AA20 |
| Operation!AA7 | Operation\|7\|Operation!r2 | Y23 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!Z10)-1)*TBA!Z10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:Z10, TBA!Z10 |
| Operation!AA8 | Operation\|8\|Operation!r2 | Y23 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!Z10)-1)*TBA!Z10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:Z10, TBA!Z10 |
| Operation!AB10 | Operation\|10\|Operation!r2 | Y24 | same_period | AB7*'Input Assumptions'!$D$20/1000 | Operation!AB7, Input Assumptions!D20 |
| Operation!AB11 | Operation\|11\|Operation!r2 | Y24 | same_period | AB8*'Input Assumptions'!$D$21/1000 | Operation!AB8, Input Assumptions!D21 |
| Operation!AB12 | Operation\|12\|Operation!r2 | Y24 | aggregation | SUM(AB10:AB11) | Operation!AB10:AB11 |
| Operation!AB14 | Operation\|14\|Operation!r2 | Y24 | cross_period | AB12*(1+'Input Assumptions'!$D$18)^(AB2-$E$2) | Operation!AB12, Input Assumptions!D18, Operation!AB2, Operation!E2 |
| Operation!AB20 | Operation\|20\|Operation!r2 | Y24 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AB2-$E$2)*TBA!AA10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AB2, Operation!E2, TBA!AA10 |
| Operation!AB21 | Operation\|21\|Operation!r2 | Y24 | aggregation | SUM(AB19:AB20) | Operation!AB19:AB20 |
| Operation!AB7 | Operation\|7\|Operation!r2 | Y24 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AA10)-1)*TBA!AA10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AA10, TBA!AA10 |
| Operation!AB8 | Operation\|8\|Operation!r2 | Y24 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AA10)-1)*TBA!AA10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AA10, TBA!AA10 |
| Operation!AC10 | Operation\|10\|Operation!r2 | Y25 | same_period | AC7*'Input Assumptions'!$D$20/1000 | Operation!AC7, Input Assumptions!D20 |
| Operation!AC11 | Operation\|11\|Operation!r2 | Y25 | same_period | AC8*'Input Assumptions'!$D$21/1000 | Operation!AC8, Input Assumptions!D21 |
| Operation!AC12 | Operation\|12\|Operation!r2 | Y25 | aggregation | SUM(AC10:AC11) | Operation!AC10:AC11 |
| Operation!AC14 | Operation\|14\|Operation!r2 | Y25 | cross_period | AC12*(1+'Input Assumptions'!$D$18)^(AC2-$E$2) | Operation!AC12, Input Assumptions!D18, Operation!AC2, Operation!E2 |
| Operation!AC20 | Operation\|20\|Operation!r2 | Y25 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AC2-$E$2)*TBA!AB10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AC2, Operation!E2, TBA!AB10 |
| Operation!AC21 | Operation\|21\|Operation!r2 | Y25 | aggregation | SUM(AC19:AC20) | Operation!AC19:AC20 |
| Operation!AC7 | Operation\|7\|Operation!r2 | Y25 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AB10)-1)*TBA!AB10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AB10, TBA!AB10 |
| Operation!AC8 | Operation\|8\|Operation!r2 | Y25 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AB10)-1)*TBA!AB10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AB10, TBA!AB10 |
| Operation!AD10 | Operation\|10\|Operation!r2 | Y26 | same_period | AD7*'Input Assumptions'!$D$20/1000 | Operation!AD7, Input Assumptions!D20 |
| Operation!AD11 | Operation\|11\|Operation!r2 | Y26 | same_period | AD8*'Input Assumptions'!$D$21/1000 | Operation!AD8, Input Assumptions!D21 |
| Operation!AD12 | Operation\|12\|Operation!r2 | Y26 | aggregation | SUM(AD10:AD11) | Operation!AD10:AD11 |
| Operation!AD14 | Operation\|14\|Operation!r2 | Y26 | cross_period | AD12*(1+'Input Assumptions'!$D$18)^(AD2-$E$2) | Operation!AD12, Input Assumptions!D18, Operation!AD2, Operation!E2 |
| Operation!AD20 | Operation\|20\|Operation!r2 | Y26 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AD2-$E$2)*TBA!AC10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AD2, Operation!E2, TBA!AC10 |
| Operation!AD21 | Operation\|21\|Operation!r2 | Y26 | aggregation | SUM(AD19:AD20) | Operation!AD19:AD20 |
| Operation!AD7 | Operation\|7\|Operation!r2 | Y26 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AC10)-1)*TBA!AC10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AC10, TBA!AC10 |
| Operation!AD8 | Operation\|8\|Operation!r2 | Y26 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AC10)-1)*TBA!AC10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AC10, TBA!AC10 |
| Operation!AE10 | Operation\|10\|Operation!r2 | Y27 | same_period | AE7*'Input Assumptions'!$D$20/1000 | Operation!AE7, Input Assumptions!D20 |
| Operation!AE11 | Operation\|11\|Operation!r2 | Y27 | same_period | AE8*'Input Assumptions'!$D$21/1000 | Operation!AE8, Input Assumptions!D21 |
| Operation!AE12 | Operation\|12\|Operation!r2 | Y27 | aggregation | SUM(AE10:AE11) | Operation!AE10:AE11 |
| Operation!AE14 | Operation\|14\|Operation!r2 | Y27 | cross_period | AE12*(1+'Input Assumptions'!$D$18)^(AE2-$E$2) | Operation!AE12, Input Assumptions!D18, Operation!AE2, Operation!E2 |
| Operation!AE20 | Operation\|20\|Operation!r2 | Y27 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AE2-$E$2)*TBA!AD10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AE2, Operation!E2, TBA!AD10 |
| Operation!AE21 | Operation\|21\|Operation!r2 | Y27 | aggregation | SUM(AE19:AE20) | Operation!AE19:AE20 |
| Operation!AE7 | Operation\|7\|Operation!r2 | Y27 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AD10)-1)*TBA!AD10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AD10, TBA!AD10 |
| Operation!AE8 | Operation\|8\|Operation!r2 | Y27 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AD10)-1)*TBA!AD10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AD10, TBA!AD10 |
| Operation!AF10 | Operation\|10\|Operation!r2 | Y28 | same_period | AF7*'Input Assumptions'!$D$20/1000 | Operation!AF7, Input Assumptions!D20 |
| Operation!AF11 | Operation\|11\|Operation!r2 | Y28 | same_period | AF8*'Input Assumptions'!$D$21/1000 | Operation!AF8, Input Assumptions!D21 |
| Operation!AF12 | Operation\|12\|Operation!r2 | Y28 | aggregation | SUM(AF10:AF11) | Operation!AF10:AF11 |
| Operation!AF14 | Operation\|14\|Operation!r2 | Y28 | cross_period | AF12*(1+'Input Assumptions'!$D$18)^(AF2-$E$2) | Operation!AF12, Input Assumptions!D18, Operation!AF2, Operation!E2 |
| Operation!AF20 | Operation\|20\|Operation!r2 | Y28 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AF2-$E$2)*TBA!AE10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AF2, Operation!E2, TBA!AE10 |
| Operation!AF21 | Operation\|21\|Operation!r2 | Y28 | aggregation | SUM(AF19:AF20) | Operation!AF19:AF20 |
| Operation!AF7 | Operation\|7\|Operation!r2 | Y28 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AE10)-1)*TBA!AE10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AE10, TBA!AE10 |
| Operation!AF8 | Operation\|8\|Operation!r2 | Y28 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AE10)-1)*TBA!AE10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AE10, TBA!AE10 |
| Operation!AG10 | Operation\|10\|Operation!r2 | Y29 | same_period | AG7*'Input Assumptions'!$D$20/1000 | Operation!AG7, Input Assumptions!D20 |
| Operation!AG11 | Operation\|11\|Operation!r2 | Y29 | same_period | AG8*'Input Assumptions'!$D$21/1000 | Operation!AG8, Input Assumptions!D21 |
| Operation!AG12 | Operation\|12\|Operation!r2 | Y29 | aggregation | SUM(AG10:AG11) | Operation!AG10:AG11 |
| Operation!AG14 | Operation\|14\|Operation!r2 | Y29 | cross_period | AG12*(1+'Input Assumptions'!$D$18)^(AG2-$E$2) | Operation!AG12, Input Assumptions!D18, Operation!AG2, Operation!E2 |
| Operation!AG20 | Operation\|20\|Operation!r2 | Y29 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AG2-$E$2)*TBA!AF10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AG2, Operation!E2, TBA!AF10 |
| Operation!AG21 | Operation\|21\|Operation!r2 | Y29 | aggregation | SUM(AG19:AG20) | Operation!AG19:AG20 |
| Operation!AG7 | Operation\|7\|Operation!r2 | Y29 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AF10)-1)*TBA!AF10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AF10, TBA!AF10 |
| Operation!AG8 | Operation\|8\|Operation!r2 | Y29 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AF10)-1)*TBA!AF10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AF10, TBA!AF10 |
| Operation!AH10 | Operation\|10\|Operation!r2 | Y30 | same_period | AH7*'Input Assumptions'!$D$20/1000 | Operation!AH7, Input Assumptions!D20 |
| Operation!AH11 | Operation\|11\|Operation!r2 | Y30 | same_period | AH8*'Input Assumptions'!$D$21/1000 | Operation!AH8, Input Assumptions!D21 |
| Operation!AH12 | Operation\|12\|Operation!r2 | Y30 | aggregation | SUM(AH10:AH11) | Operation!AH10:AH11 |
| Operation!AH14 | Operation\|14\|Operation!r2 | Y30 | cross_period | AH12*(1+'Input Assumptions'!$D$18)^(AH2-$E$2) | Operation!AH12, Input Assumptions!D18, Operation!AH2, Operation!E2 |
| Operation!AH20 | Operation\|20\|Operation!r2 | Y30 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AH2-$E$2)*TBA!AG10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AH2, Operation!E2, TBA!AG10 |
| Operation!AH21 | Operation\|21\|Operation!r2 | Y30 | aggregation | SUM(AH19:AH20) | Operation!AH19:AH20 |
| Operation!AH7 | Operation\|7\|Operation!r2 | Y30 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AG10)-1)*TBA!AG10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AG10, TBA!AG10 |
| Operation!AH8 | Operation\|8\|Operation!r2 | Y30 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AG10)-1)*TBA!AG10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AG10, TBA!AG10 |
| Operation!AI10 | Operation\|10\|Operation!r2 | Y31 | same_period | AI7*'Input Assumptions'!$D$20/1000 | Operation!AI7, Input Assumptions!D20 |
| Operation!AI11 | Operation\|11\|Operation!r2 | Y31 | same_period | AI8*'Input Assumptions'!$D$21/1000 | Operation!AI8, Input Assumptions!D21 |
| Operation!AI12 | Operation\|12\|Operation!r2 | Y31 | aggregation | SUM(AI10:AI11) | Operation!AI10:AI11 |
| Operation!AI14 | Operation\|14\|Operation!r2 | Y31 | cross_period | AI12*(1+'Input Assumptions'!$D$18)^(AI2-$E$2) | Operation!AI12, Input Assumptions!D18, Operation!AI2, Operation!E2 |
| Operation!AI20 | Operation\|20\|Operation!r2 | Y31 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AI2-$E$2)*TBA!AH10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AI2, Operation!E2, TBA!AH10 |
| Operation!AI21 | Operation\|21\|Operation!r2 | Y31 | aggregation | SUM(AI19:AI20) | Operation!AI19:AI20 |
| Operation!AI7 | Operation\|7\|Operation!r2 | Y31 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AH10)-1)*TBA!AH10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AH10, TBA!AH10 |
| Operation!AI8 | Operation\|8\|Operation!r2 | Y31 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AH10)-1)*TBA!AH10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AH10, TBA!AH10 |
| Operation!AJ10 | Operation\|10\|Operation!r2 | Y32 | same_period | AJ7*'Input Assumptions'!$D$20/1000 | Operation!AJ7, Input Assumptions!D20 |
| Operation!AJ11 | Operation\|11\|Operation!r2 | Y32 | same_period | AJ8*'Input Assumptions'!$D$21/1000 | Operation!AJ8, Input Assumptions!D21 |
| Operation!AJ12 | Operation\|12\|Operation!r2 | Y32 | aggregation | SUM(AJ10:AJ11) | Operation!AJ10:AJ11 |
| Operation!AJ14 | Operation\|14\|Operation!r2 | Y32 | cross_period | AJ12*(1+'Input Assumptions'!$D$18)^(AJ2-$E$2) | Operation!AJ12, Input Assumptions!D18, Operation!AJ2, Operation!E2 |
| Operation!AJ20 | Operation\|20\|Operation!r2 | Y32 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AJ2-$E$2)*TBA!AI10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AJ2, Operation!E2, TBA!AI10 |
| Operation!AJ21 | Operation\|21\|Operation!r2 | Y32 | aggregation | SUM(AJ19:AJ20) | Operation!AJ19:AJ20 |
| Operation!AJ7 | Operation\|7\|Operation!r2 | Y32 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AI10)-1)*TBA!AI10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AI10, TBA!AI10 |
| Operation!AJ8 | Operation\|8\|Operation!r2 | Y32 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AI10)-1)*TBA!AI10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AI10, TBA!AI10 |
| Operation!AK10 | Operation\|10\|Operation!r2 | Y33 | same_period | AK7*'Input Assumptions'!$D$20/1000 | Operation!AK7, Input Assumptions!D20 |
| Operation!AK11 | Operation\|11\|Operation!r2 | Y33 | same_period | AK8*'Input Assumptions'!$D$21/1000 | Operation!AK8, Input Assumptions!D21 |
| Operation!AK12 | Operation\|12\|Operation!r2 | Y33 | aggregation | SUM(AK10:AK11) | Operation!AK10:AK11 |
| Operation!AK14 | Operation\|14\|Operation!r2 | Y33 | cross_period | AK12*(1+'Input Assumptions'!$D$18)^(AK2-$E$2) | Operation!AK12, Input Assumptions!D18, Operation!AK2, Operation!E2 |
| Operation!AK20 | Operation\|20\|Operation!r2 | Y33 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AK2-$E$2)*TBA!AJ10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AK2, Operation!E2, TBA!AJ10 |
| Operation!AK21 | Operation\|21\|Operation!r2 | Y33 | aggregation | SUM(AK19:AK20) | Operation!AK19:AK20 |
| Operation!AK7 | Operation\|7\|Operation!r2 | Y33 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AJ10)-1)*TBA!AJ10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AJ10, TBA!AJ10 |
| Operation!AK8 | Operation\|8\|Operation!r2 | Y33 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AJ10)-1)*TBA!AJ10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AJ10, TBA!AJ10 |
| Operation!AL10 | Operation\|10\|Operation!r2 | Y34 | same_period | AL7*'Input Assumptions'!$D$20/1000 | Operation!AL7, Input Assumptions!D20 |
| Operation!AL11 | Operation\|11\|Operation!r2 | Y34 | same_period | AL8*'Input Assumptions'!$D$21/1000 | Operation!AL8, Input Assumptions!D21 |
| Operation!AL12 | Operation\|12\|Operation!r2 | Y34 | aggregation | SUM(AL10:AL11) | Operation!AL10:AL11 |
| Operation!AL14 | Operation\|14\|Operation!r2 | Y34 | cross_period | AL12*(1+'Input Assumptions'!$D$18)^(AL2-$E$2) | Operation!AL12, Input Assumptions!D18, Operation!AL2, Operation!E2 |
| Operation!AL20 | Operation\|20\|Operation!r2 | Y34 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AL2-$E$2)*TBA!AK10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AL2, Operation!E2, TBA!AK10 |
| Operation!AL21 | Operation\|21\|Operation!r2 | Y34 | aggregation | SUM(AL19:AL20) | Operation!AL19:AL20 |
| Operation!AL7 | Operation\|7\|Operation!r2 | Y34 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AK10)-1)*TBA!AK10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AK10, TBA!AK10 |
| Operation!AL8 | Operation\|8\|Operation!r2 | Y34 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AK10)-1)*TBA!AK10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AK10, TBA!AK10 |
| Operation!AM10 | Operation\|10\|Operation!r2 | Y35 | same_period | AM7*'Input Assumptions'!$D$20/1000 | Operation!AM7, Input Assumptions!D20 |
| Operation!AM11 | Operation\|11\|Operation!r2 | Y35 | same_period | AM8*'Input Assumptions'!$D$21/1000 | Operation!AM8, Input Assumptions!D21 |
| Operation!AM12 | Operation\|12\|Operation!r2 | Y35 | aggregation | SUM(AM10:AM11) | Operation!AM10:AM11 |
| Operation!AM14 | Operation\|14\|Operation!r2 | Y35 | cross_period | AM12*(1+'Input Assumptions'!$D$18)^(AM2-$E$2) | Operation!AM12, Input Assumptions!D18, Operation!AM2, Operation!E2 |
| Operation!AM20 | Operation\|20\|Operation!r2 | Y35 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AM2-$E$2)*TBA!AL10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AM2, Operation!E2, TBA!AL10 |
| Operation!AM21 | Operation\|21\|Operation!r2 | Y35 | aggregation | SUM(AM19:AM20) | Operation!AM19:AM20 |
| Operation!AM7 | Operation\|7\|Operation!r2 | Y35 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AL10)-1)*TBA!AL10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AL10, TBA!AL10 |
| Operation!AM8 | Operation\|8\|Operation!r2 | Y35 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AL10)-1)*TBA!AL10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AL10, TBA!AL10 |
| Operation!AN10 | Operation\|10\|Operation!r2 | Y36 | same_period | AN7*'Input Assumptions'!$D$20/1000 | Operation!AN7, Input Assumptions!D20 |
| Operation!AN11 | Operation\|11\|Operation!r2 | Y36 | same_period | AN8*'Input Assumptions'!$D$21/1000 | Operation!AN8, Input Assumptions!D21 |
| Operation!AN12 | Operation\|12\|Operation!r2 | Y36 | aggregation | SUM(AN10:AN11) | Operation!AN10:AN11 |
| Operation!AN14 | Operation\|14\|Operation!r2 | Y36 | cross_period | AN12*(1+'Input Assumptions'!$D$18)^(AN2-$E$2) | Operation!AN12, Input Assumptions!D18, Operation!AN2, Operation!E2 |
| Operation!AN20 | Operation\|20\|Operation!r2 | Y36 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AN2-$E$2)*TBA!AM10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AN2, Operation!E2, TBA!AM10 |
| Operation!AN21 | Operation\|21\|Operation!r2 | Y36 | aggregation | SUM(AN19:AN20) | Operation!AN19:AN20 |
| Operation!AN7 | Operation\|7\|Operation!r2 | Y36 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AM10)-1)*TBA!AM10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AM10, TBA!AM10 |
| Operation!AN8 | Operation\|8\|Operation!r2 | Y36 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AM10)-1)*TBA!AM10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AM10, TBA!AM10 |
| Operation!AO10 | Operation\|10\|Operation!r2 | Y37 | same_period | AO7*'Input Assumptions'!$D$20/1000 | Operation!AO7, Input Assumptions!D20 |
| Operation!AO11 | Operation\|11\|Operation!r2 | Y37 | same_period | AO8*'Input Assumptions'!$D$21/1000 | Operation!AO8, Input Assumptions!D21 |
| Operation!AO12 | Operation\|12\|Operation!r2 | Y37 | aggregation | SUM(AO10:AO11) | Operation!AO10:AO11 |
| Operation!AO14 | Operation\|14\|Operation!r2 | Y37 | cross_period | AO12*(1+'Input Assumptions'!$D$18)^(AO2-$E$2) | Operation!AO12, Input Assumptions!D18, Operation!AO2, Operation!E2 |
| Operation!AO20 | Operation\|20\|Operation!r2 | Y37 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AO2-$E$2)*TBA!AN10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AO2, Operation!E2, TBA!AN10 |
| Operation!AO21 | Operation\|21\|Operation!r2 | Y37 | aggregation | SUM(AO19:AO20) | Operation!AO19:AO20 |
| Operation!AO7 | Operation\|7\|Operation!r2 | Y37 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AN10)-1)*TBA!AN10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AN10, TBA!AN10 |
| Operation!AO8 | Operation\|8\|Operation!r2 | Y37 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AN10)-1)*TBA!AN10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AN10, TBA!AN10 |
| Operation!AP10 | Operation\|10\|Operation!r2 | Y38 | same_period | AP7*'Input Assumptions'!$D$20/1000 | Operation!AP7, Input Assumptions!D20 |
| Operation!AP11 | Operation\|11\|Operation!r2 | Y38 | same_period | AP8*'Input Assumptions'!$D$21/1000 | Operation!AP8, Input Assumptions!D21 |
| Operation!AP12 | Operation\|12\|Operation!r2 | Y38 | aggregation | SUM(AP10:AP11) | Operation!AP10:AP11 |
| Operation!AP14 | Operation\|14\|Operation!r2 | Y38 | cross_period | AP12*(1+'Input Assumptions'!$D$18)^(AP2-$E$2) | Operation!AP12, Input Assumptions!D18, Operation!AP2, Operation!E2 |
| Operation!AP20 | Operation\|20\|Operation!r2 | Y38 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AP2-$E$2)*TBA!AO10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AP2, Operation!E2, TBA!AO10 |
| Operation!AP21 | Operation\|21\|Operation!r2 | Y38 | aggregation | SUM(AP19:AP20) | Operation!AP19:AP20 |
| Operation!AP7 | Operation\|7\|Operation!r2 | Y38 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AO10)-1)*TBA!AO10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AO10, TBA!AO10 |
| Operation!AP8 | Operation\|8\|Operation!r2 | Y38 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AO10)-1)*TBA!AO10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AO10, TBA!AO10 |
| Operation!AQ10 | Operation\|10\|Operation!r2 | Y39 | same_period | AQ7*'Input Assumptions'!$D$20/1000 | Operation!AQ7, Input Assumptions!D20 |
| Operation!AQ11 | Operation\|11\|Operation!r2 | Y39 | same_period | AQ8*'Input Assumptions'!$D$21/1000 | Operation!AQ8, Input Assumptions!D21 |
| Operation!AQ12 | Operation\|12\|Operation!r2 | Y39 | aggregation | SUM(AQ10:AQ11) | Operation!AQ10:AQ11 |
| Operation!AQ14 | Operation\|14\|Operation!r2 | Y39 | cross_period | AQ12*(1+'Input Assumptions'!$D$18)^(AQ2-$E$2) | Operation!AQ12, Input Assumptions!D18, Operation!AQ2, Operation!E2 |
| Operation!AQ20 | Operation\|20\|Operation!r2 | Y39 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AQ2-$E$2)*TBA!AP10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AQ2, Operation!E2, TBA!AP10 |
| Operation!AQ21 | Operation\|21\|Operation!r2 | Y39 | aggregation | SUM(AQ19:AQ20) | Operation!AQ19:AQ20 |
| Operation!AQ7 | Operation\|7\|Operation!r2 | Y39 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AP10)-1)*TBA!AP10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AP10, TBA!AP10 |
| Operation!AQ8 | Operation\|8\|Operation!r2 | Y39 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AP10)-1)*TBA!AP10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AP10, TBA!AP10 |
| Operation!AR10 | Operation\|10\|Operation!r2 | Y40 | same_period | AR7*'Input Assumptions'!$D$20/1000 | Operation!AR7, Input Assumptions!D20 |
| Operation!AR11 | Operation\|11\|Operation!r2 | Y40 | same_period | AR8*'Input Assumptions'!$D$21/1000 | Operation!AR8, Input Assumptions!D21 |
| Operation!AR12 | Operation\|12\|Operation!r2 | Y40 | aggregation | SUM(AR10:AR11) | Operation!AR10:AR11 |
| Operation!AR14 | Operation\|14\|Operation!r2 | Y40 | cross_period | AR12*(1+'Input Assumptions'!$D$18)^(AR2-$E$2) | Operation!AR12, Input Assumptions!D18, Operation!AR2, Operation!E2 |
| Operation!AR20 | Operation\|20\|Operation!r2 | Y40 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(AR2-$E$2)*TBA!AQ10 | Input Assumptions!D29, Input Assumptions!D31, Operation!AR2, Operation!E2, TBA!AQ10 |
| Operation!AR21 | Operation\|21\|Operation!r2 | Y40 | aggregation | SUM(AR19:AR20) | Operation!AR19:AR20 |
| Operation!AR7 | Operation\|7\|Operation!r2 | Y40 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AQ10)-1)*TBA!AQ10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:AQ10, TBA!AQ10 |
| Operation!AR8 | Operation\|8\|Operation!r2 | Y40 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!AQ10)-1)*TBA!AQ10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:AQ10, TBA!AQ10 |
| Operation!D10 | Operation\|10\|Operation!r2 |  | aggregation | SUM(E10:AR10) | Operation!E10:AR10 |
| Operation!D11 | Operation\|11\|Operation!r2 |  | aggregation | SUM(E11:AR11) | Operation!E11:AR11 |
| Operation!D12 | Operation\|12\|Operation!r2 |  | aggregation | SUM(E12:AR12) | Operation!E12:AR12 |
| Operation!D14 | Operation\|14\|Operation!r2 |  | aggregation | SUM(E14:AR14) | Operation!E14:AR14 |
| Operation!D21 | Operation\|21\|Operation!r2 |  | aggregation | SUM(E21:AR21) | Operation!E21:AR21 |
| Operation!E10 | Operation\|10\|Operation!r2 | Y1 | same_period | E7*'Input Assumptions'!$D$20/1000 | Operation!E7, Input Assumptions!D20 |
| Operation!E11 | Operation\|11\|Operation!r2 | Y1 | same_period | E8*'Input Assumptions'!$D$21/1000 | Operation!E8, Input Assumptions!D21 |
| Operation!E12 | Operation\|12\|Operation!r2 | Y1 | aggregation | SUM(E10:E11) | Operation!E10:E11 |
| Operation!E14 | Operation\|14\|Operation!r2 | Y1 | same_period | E12*(1+'Input Assumptions'!$D$18)^(E2-$E$2) | Operation!E12, Input Assumptions!D18, Operation!E2 |
| Operation!E20 | Operation\|20\|Operation!r2 | Y1 | same_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(E2-$E$2)*TBA!D10 | Input Assumptions!D29, Input Assumptions!D31, Operation!E2, TBA!D10 |
| Operation!E21 | Operation\|21\|Operation!r2 | Y1 | aggregation | SUM(E19:E20) | Operation!E19:E20 |
| Operation!E7 | Operation\|7\|Operation!r2 | Y1 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!D10)-1)*TBA!D10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:D10, TBA!D10 |
| Operation!E8 | Operation\|8\|Operation!r2 | Y1 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!D10)-1)*TBA!D10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:D10, TBA!D10 |
| Operation!F10 | Operation\|10\|Operation!r2 | Y2 | same_period | F7*'Input Assumptions'!$D$20/1000 | Operation!F7, Input Assumptions!D20 |
| Operation!F11 | Operation\|11\|Operation!r2 | Y2 | same_period | F8*'Input Assumptions'!$D$21/1000 | Operation!F8, Input Assumptions!D21 |
| Operation!F12 | Operation\|12\|Operation!r2 | Y2 | aggregation | SUM(F10:F11) | Operation!F10:F11 |
| Operation!F14 | Operation\|14\|Operation!r2 | Y2 | cross_period | F12*(1+'Input Assumptions'!$D$18)^(F2-$E$2) | Operation!F12, Input Assumptions!D18, Operation!F2, Operation!E2 |
| Operation!F20 | Operation\|20\|Operation!r2 | Y2 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(F2-$E$2)*TBA!E10 | Input Assumptions!D29, Input Assumptions!D31, Operation!F2, Operation!E2, TBA!E10 |
| Operation!F21 | Operation\|21\|Operation!r2 | Y2 | aggregation | SUM(F19:F20) | Operation!F19:F20 |
| Operation!F7 | Operation\|7\|Operation!r2 | Y2 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!E10)-1)*TBA!E10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:E10, TBA!E10 |
| Operation!F8 | Operation\|8\|Operation!r2 | Y2 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!E10)-1)*TBA!E10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:E10, TBA!E10 |
| Operation!G10 | Operation\|10\|Operation!r2 | Y3 | same_period | G7*'Input Assumptions'!$D$20/1000 | Operation!G7, Input Assumptions!D20 |
| Operation!G11 | Operation\|11\|Operation!r2 | Y3 | same_period | G8*'Input Assumptions'!$D$21/1000 | Operation!G8, Input Assumptions!D21 |
| Operation!G12 | Operation\|12\|Operation!r2 | Y3 | aggregation | SUM(G10:G11) | Operation!G10:G11 |
| Operation!G14 | Operation\|14\|Operation!r2 | Y3 | cross_period | G12*(1+'Input Assumptions'!$D$18)^(G2-$E$2) | Operation!G12, Input Assumptions!D18, Operation!G2, Operation!E2 |
| Operation!G20 | Operation\|20\|Operation!r2 | Y3 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(G2-$E$2)*TBA!F10 | Input Assumptions!D29, Input Assumptions!D31, Operation!G2, Operation!E2, TBA!F10 |
| Operation!G21 | Operation\|21\|Operation!r2 | Y3 | aggregation | SUM(G19:G20) | Operation!G19:G20 |
| Operation!G7 | Operation\|7\|Operation!r2 | Y3 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!F10)-1)*TBA!F10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:F10, TBA!F10 |
| Operation!G8 | Operation\|8\|Operation!r2 | Y3 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!F10)-1)*TBA!F10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:F10, TBA!F10 |
| Operation!H10 | Operation\|10\|Operation!r2 | Y4 | same_period | H7*'Input Assumptions'!$D$20/1000 | Operation!H7, Input Assumptions!D20 |
| Operation!H11 | Operation\|11\|Operation!r2 | Y4 | same_period | H8*'Input Assumptions'!$D$21/1000 | Operation!H8, Input Assumptions!D21 |
| Operation!H12 | Operation\|12\|Operation!r2 | Y4 | aggregation | SUM(H10:H11) | Operation!H10:H11 |
| Operation!H14 | Operation\|14\|Operation!r2 | Y4 | cross_period | H12*(1+'Input Assumptions'!$D$18)^(H2-$E$2) | Operation!H12, Input Assumptions!D18, Operation!H2, Operation!E2 |
| Operation!H20 | Operation\|20\|Operation!r2 | Y4 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(H2-$E$2)*TBA!G10 | Input Assumptions!D29, Input Assumptions!D31, Operation!H2, Operation!E2, TBA!G10 |
| Operation!H21 | Operation\|21\|Operation!r2 | Y4 | aggregation | SUM(H19:H20) | Operation!H19:H20 |
| Operation!H7 | Operation\|7\|Operation!r2 | Y4 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!G10)-1)*TBA!G10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:G10, TBA!G10 |
| Operation!H8 | Operation\|8\|Operation!r2 | Y4 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!G10)-1)*TBA!G10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:G10, TBA!G10 |
| Operation!I10 | Operation\|10\|Operation!r2 | Y5 | same_period | I7*'Input Assumptions'!$D$20/1000 | Operation!I7, Input Assumptions!D20 |
| Operation!I11 | Operation\|11\|Operation!r2 | Y5 | same_period | I8*'Input Assumptions'!$D$21/1000 | Operation!I8, Input Assumptions!D21 |
| Operation!I12 | Operation\|12\|Operation!r2 | Y5 | aggregation | SUM(I10:I11) | Operation!I10:I11 |
| Operation!I14 | Operation\|14\|Operation!r2 | Y5 | cross_period | I12*(1+'Input Assumptions'!$D$18)^(I2-$E$2) | Operation!I12, Input Assumptions!D18, Operation!I2, Operation!E2 |
| Operation!I20 | Operation\|20\|Operation!r2 | Y5 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(I2-$E$2)*TBA!H10 | Input Assumptions!D29, Input Assumptions!D31, Operation!I2, Operation!E2, TBA!H10 |
| Operation!I21 | Operation\|21\|Operation!r2 | Y5 | aggregation | SUM(I19:I20) | Operation!I19:I20 |
| Operation!I7 | Operation\|7\|Operation!r2 | Y5 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!H10)-1)*TBA!H10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:H10, TBA!H10 |
| Operation!I8 | Operation\|8\|Operation!r2 | Y5 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!H10)-1)*TBA!H10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:H10, TBA!H10 |
| Operation!J10 | Operation\|10\|Operation!r2 | Y6 | same_period | J7*'Input Assumptions'!$D$20/1000 | Operation!J7, Input Assumptions!D20 |
| Operation!J11 | Operation\|11\|Operation!r2 | Y6 | same_period | J8*'Input Assumptions'!$D$21/1000 | Operation!J8, Input Assumptions!D21 |
| Operation!J12 | Operation\|12\|Operation!r2 | Y6 | aggregation | SUM(J10:J11) | Operation!J10:J11 |
| Operation!J14 | Operation\|14\|Operation!r2 | Y6 | cross_period | J12*(1+'Input Assumptions'!$D$18)^(J2-$E$2) | Operation!J12, Input Assumptions!D18, Operation!J2, Operation!E2 |
| Operation!J20 | Operation\|20\|Operation!r2 | Y6 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(J2-$E$2)*TBA!I10 | Input Assumptions!D29, Input Assumptions!D31, Operation!J2, Operation!E2, TBA!I10 |
| Operation!J21 | Operation\|21\|Operation!r2 | Y6 | aggregation | SUM(J19:J20) | Operation!J19:J20 |
| Operation!J7 | Operation\|7\|Operation!r2 | Y6 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!I10)-1)*TBA!I10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:I10, TBA!I10 |
| Operation!J8 | Operation\|8\|Operation!r2 | Y6 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!I10)-1)*TBA!I10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:I10, TBA!I10 |
| Operation!K10 | Operation\|10\|Operation!r2 | Y7 | same_period | K7*'Input Assumptions'!$D$20/1000 | Operation!K7, Input Assumptions!D20 |
| Operation!K11 | Operation\|11\|Operation!r2 | Y7 | same_period | K8*'Input Assumptions'!$D$21/1000 | Operation!K8, Input Assumptions!D21 |
| Operation!K12 | Operation\|12\|Operation!r2 | Y7 | aggregation | SUM(K10:K11) | Operation!K10:K11 |
| Operation!K14 | Operation\|14\|Operation!r2 | Y7 | cross_period | K12*(1+'Input Assumptions'!$D$18)^(K2-$E$2) | Operation!K12, Input Assumptions!D18, Operation!K2, Operation!E2 |
| Operation!K20 | Operation\|20\|Operation!r2 | Y7 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(K2-$E$2)*TBA!J10 | Input Assumptions!D29, Input Assumptions!D31, Operation!K2, Operation!E2, TBA!J10 |
| Operation!K21 | Operation\|21\|Operation!r2 | Y7 | aggregation | SUM(K19:K20) | Operation!K19:K20 |
| Operation!K7 | Operation\|7\|Operation!r2 | Y7 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!J10)-1)*TBA!J10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:J10, TBA!J10 |
| Operation!K8 | Operation\|8\|Operation!r2 | Y7 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!J10)-1)*TBA!J10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:J10, TBA!J10 |
| Operation!L10 | Operation\|10\|Operation!r2 | Y8 | same_period | L7*'Input Assumptions'!$D$20/1000 | Operation!L7, Input Assumptions!D20 |
| Operation!L11 | Operation\|11\|Operation!r2 | Y8 | same_period | L8*'Input Assumptions'!$D$21/1000 | Operation!L8, Input Assumptions!D21 |
| Operation!L12 | Operation\|12\|Operation!r2 | Y8 | aggregation | SUM(L10:L11) | Operation!L10:L11 |
| Operation!L14 | Operation\|14\|Operation!r2 | Y8 | cross_period | L12*(1+'Input Assumptions'!$D$18)^(L2-$E$2) | Operation!L12, Input Assumptions!D18, Operation!L2, Operation!E2 |
| Operation!L20 | Operation\|20\|Operation!r2 | Y8 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(L2-$E$2)*TBA!K10 | Input Assumptions!D29, Input Assumptions!D31, Operation!L2, Operation!E2, TBA!K10 |
| Operation!L21 | Operation\|21\|Operation!r2 | Y8 | aggregation | SUM(L19:L20) | Operation!L19:L20 |
| Operation!L7 | Operation\|7\|Operation!r2 | Y8 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!K10)-1)*TBA!K10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:K10, TBA!K10 |
| Operation!L8 | Operation\|8\|Operation!r2 | Y8 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!K10)-1)*TBA!K10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:K10, TBA!K10 |
| Operation!M10 | Operation\|10\|Operation!r2 | Y9 | same_period | M7*'Input Assumptions'!$D$20/1000 | Operation!M7, Input Assumptions!D20 |
| Operation!M11 | Operation\|11\|Operation!r2 | Y9 | same_period | M8*'Input Assumptions'!$D$21/1000 | Operation!M8, Input Assumptions!D21 |
| Operation!M12 | Operation\|12\|Operation!r2 | Y9 | aggregation | SUM(M10:M11) | Operation!M10:M11 |
| Operation!M14 | Operation\|14\|Operation!r2 | Y9 | cross_period | M12*(1+'Input Assumptions'!$D$18)^(M2-$E$2) | Operation!M12, Input Assumptions!D18, Operation!M2, Operation!E2 |
| Operation!M20 | Operation\|20\|Operation!r2 | Y9 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(M2-$E$2)*TBA!L10 | Input Assumptions!D29, Input Assumptions!D31, Operation!M2, Operation!E2, TBA!L10 |
| Operation!M21 | Operation\|21\|Operation!r2 | Y9 | aggregation | SUM(M19:M20) | Operation!M19:M20 |
| Operation!M7 | Operation\|7\|Operation!r2 | Y9 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!L10)-1)*TBA!L10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:L10, TBA!L10 |
| Operation!M8 | Operation\|8\|Operation!r2 | Y9 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!L10)-1)*TBA!L10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:L10, TBA!L10 |
| Operation!N10 | Operation\|10\|Operation!r2 | Y10 | same_period | N7*'Input Assumptions'!$D$20/1000 | Operation!N7, Input Assumptions!D20 |
| Operation!N11 | Operation\|11\|Operation!r2 | Y10 | same_period | N8*'Input Assumptions'!$D$21/1000 | Operation!N8, Input Assumptions!D21 |
| Operation!N12 | Operation\|12\|Operation!r2 | Y10 | aggregation | SUM(N10:N11) | Operation!N10:N11 |
| Operation!N14 | Operation\|14\|Operation!r2 | Y10 | cross_period | N12*(1+'Input Assumptions'!$D$18)^(N2-$E$2) | Operation!N12, Input Assumptions!D18, Operation!N2, Operation!E2 |
| Operation!N20 | Operation\|20\|Operation!r2 | Y10 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(N2-$E$2)*TBA!M10 | Input Assumptions!D29, Input Assumptions!D31, Operation!N2, Operation!E2, TBA!M10 |
| Operation!N21 | Operation\|21\|Operation!r2 | Y10 | aggregation | SUM(N19:N20) | Operation!N19:N20 |
| Operation!N7 | Operation\|7\|Operation!r2 | Y10 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!M10)-1)*TBA!M10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:M10, TBA!M10 |
| Operation!N8 | Operation\|8\|Operation!r2 | Y10 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!M10)-1)*TBA!M10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:M10, TBA!M10 |
| Operation!O10 | Operation\|10\|Operation!r2 | Y11 | same_period | O7*'Input Assumptions'!$D$20/1000 | Operation!O7, Input Assumptions!D20 |
| Operation!O11 | Operation\|11\|Operation!r2 | Y11 | same_period | O8*'Input Assumptions'!$D$21/1000 | Operation!O8, Input Assumptions!D21 |
| Operation!O12 | Operation\|12\|Operation!r2 | Y11 | aggregation | SUM(O10:O11) | Operation!O10:O11 |
| Operation!O14 | Operation\|14\|Operation!r2 | Y11 | cross_period | O12*(1+'Input Assumptions'!$D$18)^(O2-$E$2) | Operation!O12, Input Assumptions!D18, Operation!O2, Operation!E2 |
| Operation!O20 | Operation\|20\|Operation!r2 | Y11 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(O2-$E$2)*TBA!N10 | Input Assumptions!D29, Input Assumptions!D31, Operation!O2, Operation!E2, TBA!N10 |
| Operation!O21 | Operation\|21\|Operation!r2 | Y11 | aggregation | SUM(O19:O20) | Operation!O19:O20 |
| Operation!O7 | Operation\|7\|Operation!r2 | Y11 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!N10)-1)*TBA!N10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:N10, TBA!N10 |
| Operation!O8 | Operation\|8\|Operation!r2 | Y11 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!N10)-1)*TBA!N10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:N10, TBA!N10 |
| Operation!P10 | Operation\|10\|Operation!r2 | Y12 | same_period | P7*'Input Assumptions'!$D$20/1000 | Operation!P7, Input Assumptions!D20 |
| Operation!P11 | Operation\|11\|Operation!r2 | Y12 | same_period | P8*'Input Assumptions'!$D$21/1000 | Operation!P8, Input Assumptions!D21 |
| Operation!P12 | Operation\|12\|Operation!r2 | Y12 | aggregation | SUM(P10:P11) | Operation!P10:P11 |
| Operation!P14 | Operation\|14\|Operation!r2 | Y12 | cross_period | P12*(1+'Input Assumptions'!$D$18)^(P2-$E$2) | Operation!P12, Input Assumptions!D18, Operation!P2, Operation!E2 |
| Operation!P20 | Operation\|20\|Operation!r2 | Y12 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(P2-$E$2)*TBA!O10 | Input Assumptions!D29, Input Assumptions!D31, Operation!P2, Operation!E2, TBA!O10 |
| Operation!P21 | Operation\|21\|Operation!r2 | Y12 | aggregation | SUM(P19:P20) | Operation!P19:P20 |
| Operation!P7 | Operation\|7\|Operation!r2 | Y12 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!O10)-1)*TBA!O10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:O10, TBA!O10 |
| Operation!P8 | Operation\|8\|Operation!r2 | Y12 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!O10)-1)*TBA!O10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:O10, TBA!O10 |
| Operation!Q10 | Operation\|10\|Operation!r2 | Y13 | same_period | Q7*'Input Assumptions'!$D$20/1000 | Operation!Q7, Input Assumptions!D20 |
| Operation!Q11 | Operation\|11\|Operation!r2 | Y13 | same_period | Q8*'Input Assumptions'!$D$21/1000 | Operation!Q8, Input Assumptions!D21 |
| Operation!Q12 | Operation\|12\|Operation!r2 | Y13 | aggregation | SUM(Q10:Q11) | Operation!Q10:Q11 |
| Operation!Q14 | Operation\|14\|Operation!r2 | Y13 | cross_period | Q12*(1+'Input Assumptions'!$D$18)^(Q2-$E$2) | Operation!Q12, Input Assumptions!D18, Operation!Q2, Operation!E2 |
| Operation!Q20 | Operation\|20\|Operation!r2 | Y13 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(Q2-$E$2)*TBA!P10 | Input Assumptions!D29, Input Assumptions!D31, Operation!Q2, Operation!E2, TBA!P10 |
| Operation!Q21 | Operation\|21\|Operation!r2 | Y13 | aggregation | SUM(Q19:Q20) | Operation!Q19:Q20 |
| Operation!Q7 | Operation\|7\|Operation!r2 | Y13 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!P10)-1)*TBA!P10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:P10, TBA!P10 |
| Operation!Q8 | Operation\|8\|Operation!r2 | Y13 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!P10)-1)*TBA!P10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:P10, TBA!P10 |
| Operation!R10 | Operation\|10\|Operation!r2 | Y14 | same_period | R7*'Input Assumptions'!$D$20/1000 | Operation!R7, Input Assumptions!D20 |
| Operation!R11 | Operation\|11\|Operation!r2 | Y14 | same_period | R8*'Input Assumptions'!$D$21/1000 | Operation!R8, Input Assumptions!D21 |
| Operation!R12 | Operation\|12\|Operation!r2 | Y14 | aggregation | SUM(R10:R11) | Operation!R10:R11 |
| Operation!R14 | Operation\|14\|Operation!r2 | Y14 | cross_period | R12*(1+'Input Assumptions'!$D$18)^(R2-$E$2) | Operation!R12, Input Assumptions!D18, Operation!R2, Operation!E2 |
| Operation!R20 | Operation\|20\|Operation!r2 | Y14 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(R2-$E$2)*TBA!Q10 | Input Assumptions!D29, Input Assumptions!D31, Operation!R2, Operation!E2, TBA!Q10 |
| Operation!R21 | Operation\|21\|Operation!r2 | Y14 | aggregation | SUM(R19:R20) | Operation!R19:R20 |
| Operation!R7 | Operation\|7\|Operation!r2 | Y14 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!Q10)-1)*TBA!Q10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:Q10, TBA!Q10 |
| Operation!R8 | Operation\|8\|Operation!r2 | Y14 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!Q10)-1)*TBA!Q10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:Q10, TBA!Q10 |
| Operation!S10 | Operation\|10\|Operation!r2 | Y15 | same_period | S7*'Input Assumptions'!$D$20/1000 | Operation!S7, Input Assumptions!D20 |
| Operation!S11 | Operation\|11\|Operation!r2 | Y15 | same_period | S8*'Input Assumptions'!$D$21/1000 | Operation!S8, Input Assumptions!D21 |
| Operation!S12 | Operation\|12\|Operation!r2 | Y15 | aggregation | SUM(S10:S11) | Operation!S10:S11 |
| Operation!S14 | Operation\|14\|Operation!r2 | Y15 | cross_period | S12*(1+'Input Assumptions'!$D$18)^(S2-$E$2) | Operation!S12, Input Assumptions!D18, Operation!S2, Operation!E2 |
| Operation!S20 | Operation\|20\|Operation!r2 | Y15 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(S2-$E$2)*TBA!R10 | Input Assumptions!D29, Input Assumptions!D31, Operation!S2, Operation!E2, TBA!R10 |
| Operation!S21 | Operation\|21\|Operation!r2 | Y15 | aggregation | SUM(S19:S20) | Operation!S19:S20 |
| Operation!S7 | Operation\|7\|Operation!r2 | Y15 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!R10)-1)*TBA!R10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:R10, TBA!R10 |
| Operation!S8 | Operation\|8\|Operation!r2 | Y15 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!R10)-1)*TBA!R10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:R10, TBA!R10 |
| Operation!T10 | Operation\|10\|Operation!r2 | Y16 | same_period | T7*'Input Assumptions'!$D$20/1000 | Operation!T7, Input Assumptions!D20 |
| Operation!T11 | Operation\|11\|Operation!r2 | Y16 | same_period | T8*'Input Assumptions'!$D$21/1000 | Operation!T8, Input Assumptions!D21 |
| Operation!T12 | Operation\|12\|Operation!r2 | Y16 | aggregation | SUM(T10:T11) | Operation!T10:T11 |
| Operation!T14 | Operation\|14\|Operation!r2 | Y16 | cross_period | T12*(1+'Input Assumptions'!$D$18)^(T2-$E$2) | Operation!T12, Input Assumptions!D18, Operation!T2, Operation!E2 |
| Operation!T20 | Operation\|20\|Operation!r2 | Y16 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(T2-$E$2)*TBA!S10 | Input Assumptions!D29, Input Assumptions!D31, Operation!T2, Operation!E2, TBA!S10 |
| Operation!T21 | Operation\|21\|Operation!r2 | Y16 | aggregation | SUM(T19:T20) | Operation!T19:T20 |
| Operation!T7 | Operation\|7\|Operation!r2 | Y16 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!S10)-1)*TBA!S10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:S10, TBA!S10 |
| Operation!T8 | Operation\|8\|Operation!r2 | Y16 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!S10)-1)*TBA!S10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:S10, TBA!S10 |
| Operation!U10 | Operation\|10\|Operation!r2 | Y17 | same_period | U7*'Input Assumptions'!$D$20/1000 | Operation!U7, Input Assumptions!D20 |
| Operation!U11 | Operation\|11\|Operation!r2 | Y17 | same_period | U8*'Input Assumptions'!$D$21/1000 | Operation!U8, Input Assumptions!D21 |
| Operation!U12 | Operation\|12\|Operation!r2 | Y17 | aggregation | SUM(U10:U11) | Operation!U10:U11 |
| Operation!U14 | Operation\|14\|Operation!r2 | Y17 | cross_period | U12*(1+'Input Assumptions'!$D$18)^(U2-$E$2) | Operation!U12, Input Assumptions!D18, Operation!U2, Operation!E2 |
| Operation!U20 | Operation\|20\|Operation!r2 | Y17 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(U2-$E$2)*TBA!T10 | Input Assumptions!D29, Input Assumptions!D31, Operation!U2, Operation!E2, TBA!T10 |
| Operation!U21 | Operation\|21\|Operation!r2 | Y17 | aggregation | SUM(U19:U20) | Operation!U19:U20 |
| Operation!U7 | Operation\|7\|Operation!r2 | Y17 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!T10)-1)*TBA!T10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:T10, TBA!T10 |
| Operation!U8 | Operation\|8\|Operation!r2 | Y17 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!T10)-1)*TBA!T10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:T10, TBA!T10 |
| Operation!V10 | Operation\|10\|Operation!r2 | Y18 | same_period | V7*'Input Assumptions'!$D$20/1000 | Operation!V7, Input Assumptions!D20 |
| Operation!V11 | Operation\|11\|Operation!r2 | Y18 | same_period | V8*'Input Assumptions'!$D$21/1000 | Operation!V8, Input Assumptions!D21 |
| Operation!V12 | Operation\|12\|Operation!r2 | Y18 | aggregation | SUM(V10:V11) | Operation!V10:V11 |
| Operation!V14 | Operation\|14\|Operation!r2 | Y18 | cross_period | V12*(1+'Input Assumptions'!$D$18)^(V2-$E$2) | Operation!V12, Input Assumptions!D18, Operation!V2, Operation!E2 |
| Operation!V20 | Operation\|20\|Operation!r2 | Y18 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(V2-$E$2)*TBA!U10 | Input Assumptions!D29, Input Assumptions!D31, Operation!V2, Operation!E2, TBA!U10 |
| Operation!V21 | Operation\|21\|Operation!r2 | Y18 | aggregation | SUM(V19:V20) | Operation!V19:V20 |
| Operation!V7 | Operation\|7\|Operation!r2 | Y18 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!U10)-1)*TBA!U10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:U10, TBA!U10 |
| Operation!V8 | Operation\|8\|Operation!r2 | Y18 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!U10)-1)*TBA!U10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:U10, TBA!U10 |
| Operation!W10 | Operation\|10\|Operation!r2 | Y19 | same_period | W7*'Input Assumptions'!$D$20/1000 | Operation!W7, Input Assumptions!D20 |
| Operation!W11 | Operation\|11\|Operation!r2 | Y19 | same_period | W8*'Input Assumptions'!$D$21/1000 | Operation!W8, Input Assumptions!D21 |
| Operation!W12 | Operation\|12\|Operation!r2 | Y19 | aggregation | SUM(W10:W11) | Operation!W10:W11 |
| Operation!W14 | Operation\|14\|Operation!r2 | Y19 | cross_period | W12*(1+'Input Assumptions'!$D$18)^(W2-$E$2) | Operation!W12, Input Assumptions!D18, Operation!W2, Operation!E2 |
| Operation!W20 | Operation\|20\|Operation!r2 | Y19 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(W2-$E$2)*TBA!V10 | Input Assumptions!D29, Input Assumptions!D31, Operation!W2, Operation!E2, TBA!V10 |
| Operation!W21 | Operation\|21\|Operation!r2 | Y19 | aggregation | SUM(W19:W20) | Operation!W19:W20 |
| Operation!W7 | Operation\|7\|Operation!r2 | Y19 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!V10)-1)*TBA!V10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:V10, TBA!V10 |
| Operation!W8 | Operation\|8\|Operation!r2 | Y19 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!V10)-1)*TBA!V10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:V10, TBA!V10 |
| Operation!X10 | Operation\|10\|Operation!r2 | Y20 | same_period | X7*'Input Assumptions'!$D$20/1000 | Operation!X7, Input Assumptions!D20 |
| Operation!X11 | Operation\|11\|Operation!r2 | Y20 | same_period | X8*'Input Assumptions'!$D$21/1000 | Operation!X8, Input Assumptions!D21 |
| Operation!X12 | Operation\|12\|Operation!r2 | Y20 | aggregation | SUM(X10:X11) | Operation!X10:X11 |
| Operation!X14 | Operation\|14\|Operation!r2 | Y20 | cross_period | X12*(1+'Input Assumptions'!$D$18)^(X2-$E$2) | Operation!X12, Input Assumptions!D18, Operation!X2, Operation!E2 |
| Operation!X20 | Operation\|20\|Operation!r2 | Y20 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(X2-$E$2)*TBA!W10 | Input Assumptions!D29, Input Assumptions!D31, Operation!X2, Operation!E2, TBA!W10 |
| Operation!X21 | Operation\|21\|Operation!r2 | Y20 | aggregation | SUM(X19:X20) | Operation!X19:X20 |
| Operation!X7 | Operation\|7\|Operation!r2 | Y20 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!W10)-1)*TBA!W10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:W10, TBA!W10 |
| Operation!X8 | Operation\|8\|Operation!r2 | Y20 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!W10)-1)*TBA!W10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:W10, TBA!W10 |
| Operation!Y10 | Operation\|10\|Operation!r2 | Y21 | same_period | Y7*'Input Assumptions'!$D$20/1000 | Operation!Y7, Input Assumptions!D20 |
| Operation!Y11 | Operation\|11\|Operation!r2 | Y21 | same_period | Y8*'Input Assumptions'!$D$21/1000 | Operation!Y8, Input Assumptions!D21 |
| Operation!Y12 | Operation\|12\|Operation!r2 | Y21 | aggregation | SUM(Y10:Y11) | Operation!Y10:Y11 |
| Operation!Y14 | Operation\|14\|Operation!r2 | Y21 | cross_period | Y12*(1+'Input Assumptions'!$D$18)^(Y2-$E$2) | Operation!Y12, Input Assumptions!D18, Operation!Y2, Operation!E2 |
| Operation!Y20 | Operation\|20\|Operation!r2 | Y21 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(Y2-$E$2)*TBA!X10 | Input Assumptions!D29, Input Assumptions!D31, Operation!Y2, Operation!E2, TBA!X10 |
| Operation!Y21 | Operation\|21\|Operation!r2 | Y21 | aggregation | SUM(Y19:Y20) | Operation!Y19:Y20 |
| Operation!Y7 | Operation\|7\|Operation!r2 | Y21 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!X10)-1)*TBA!X10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:X10, TBA!X10 |
| Operation!Y8 | Operation\|8\|Operation!r2 | Y21 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!X10)-1)*TBA!X10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:X10, TBA!X10 |
| Operation!Z10 | Operation\|10\|Operation!r2 | Y22 | same_period | Z7*'Input Assumptions'!$D$20/1000 | Operation!Z7, Input Assumptions!D20 |
| Operation!Z11 | Operation\|11\|Operation!r2 | Y22 | same_period | Z8*'Input Assumptions'!$D$21/1000 | Operation!Z8, Input Assumptions!D21 |
| Operation!Z12 | Operation\|12\|Operation!r2 | Y22 | aggregation | SUM(Z10:Z11) | Operation!Z10:Z11 |
| Operation!Z14 | Operation\|14\|Operation!r2 | Y22 | cross_period | Z12*(1+'Input Assumptions'!$D$18)^(Z2-$E$2) | Operation!Z12, Input Assumptions!D18, Operation!Z2, Operation!E2 |
| Operation!Z20 | Operation\|20\|Operation!r2 | Y22 | cross_period | 'Input Assumptions'!$D$29/1000*(1+'Input Assumptions'!$D$31)^(Z2-$E$2)*TBA!Y10 | Input Assumptions!D29, Input Assumptions!D31, Operation!Z2, Operation!E2, TBA!Y10 |
| Operation!Z21 | Operation\|21\|Operation!r2 | Y22 | aggregation | SUM(Z19:Z20) | Operation!Z19:Z20 |
| Operation!Z7 | Operation\|7\|Operation!r2 | Y22 | aggregation | 'Input Assumptions'!$D$14*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!Y10)-1)*TBA!Y10 | Input Assumptions!D14, Input Assumptions!D17, TBA!D10:Y10, TBA!Y10 |
| Operation!Z8 | Operation\|8\|Operation!r2 | Y22 | aggregation | 'Input Assumptions'!$D$15*(1+'Input Assumptions'!$D$17)^(SUM(TBA!$D$10:'TBA'!Y10)-1)*TBA!Y10 | Input Assumptions!D15, Input Assumptions!D17, TBA!D10:Y10, TBA!Y10 |
| P&L!AA11 | P&L\|11\|P&L!r2 | Y22 | same_period | -Operation!Z21 | Operation!Z21 |
| P&L!AA13 | P&L\|13\|P&L!r2 | Y22 | aggregation | SUM(AA9:AA12) | P&L!AA9:AA12 |
| P&L!AA15 | P&L\|15\|P&L!r2 | Y22 | same_period | Amortization!Z13 | Amortization!Z13 |
| P&L!AA17 | P&L\|17\|P&L!r2 | Y22 | aggregation | SUM(AA13:AA16) | P&L!AA13:AA16 |
| P&L!AA19 | P&L\|19\|P&L!r2 | Y22 | same_period | Debt!AA14 | Debt!AA14 |
| P&L!AA21 | P&L\|21\|P&L!r2 | Y22 | aggregation | SUM(AA17:AA20) | P&L!AA17:AA20 |
| P&L!AA23 | P&L\|23\|P&L!r2 | Y22 | conditional | IF(AA21<0,0,-'Input Assumptions'!$D$44*'P&L'!AA21) | P&L!AA21, Input Assumptions!D44 |
| P&L!AA25 | P&L\|25\|P&L!r2 | Y22 | aggregation | SUM(AA21:AA24) | P&L!AA21:AA24 |
| P&L!AA9 | P&L\|9\|P&L!r2 | Y22 | same_period | Operation!Z14 | Operation!Z14 |
| P&L!AB11 | P&L\|11\|P&L!r2 | Y23 | same_period | -Operation!AA21 | Operation!AA21 |
| P&L!AB13 | P&L\|13\|P&L!r2 | Y23 | aggregation | SUM(AB9:AB12) | P&L!AB9:AB12 |
| P&L!AB15 | P&L\|15\|P&L!r2 | Y23 | same_period | Amortization!AA13 | Amortization!AA13 |
| P&L!AB17 | P&L\|17\|P&L!r2 | Y23 | aggregation | SUM(AB13:AB16) | P&L!AB13:AB16 |
| P&L!AB19 | P&L\|19\|P&L!r2 | Y23 | same_period | Debt!AB14 | Debt!AB14 |
| P&L!AB21 | P&L\|21\|P&L!r2 | Y23 | aggregation | SUM(AB17:AB20) | P&L!AB17:AB20 |
| P&L!AB23 | P&L\|23\|P&L!r2 | Y23 | conditional | IF(AB21<0,0,-'Input Assumptions'!$D$44*'P&L'!AB21) | P&L!AB21, Input Assumptions!D44 |
| P&L!AB25 | P&L\|25\|P&L!r2 | Y23 | aggregation | SUM(AB21:AB24) | P&L!AB21:AB24 |
| P&L!AB9 | P&L\|9\|P&L!r2 | Y23 | same_period | Operation!AA14 | Operation!AA14 |
| P&L!AC11 | P&L\|11\|P&L!r2 | Y24 | same_period | -Operation!AB21 | Operation!AB21 |
| P&L!AC13 | P&L\|13\|P&L!r2 | Y24 | aggregation | SUM(AC9:AC12) | P&L!AC9:AC12 |
| P&L!AC15 | P&L\|15\|P&L!r2 | Y24 | same_period | Amortization!AB13 | Amortization!AB13 |
| P&L!AC17 | P&L\|17\|P&L!r2 | Y24 | aggregation | SUM(AC13:AC16) | P&L!AC13:AC16 |
| P&L!AC19 | P&L\|19\|P&L!r2 | Y24 | same_period | Debt!AC14 | Debt!AC14 |
| P&L!AC21 | P&L\|21\|P&L!r2 | Y24 | aggregation | SUM(AC17:AC20) | P&L!AC17:AC20 |
| P&L!AC23 | P&L\|23\|P&L!r2 | Y24 | conditional | IF(AC21<0,0,-'Input Assumptions'!$D$44*'P&L'!AC21) | P&L!AC21, Input Assumptions!D44 |
| P&L!AC25 | P&L\|25\|P&L!r2 | Y24 | aggregation | SUM(AC21:AC24) | P&L!AC21:AC24 |
| P&L!AC9 | P&L\|9\|P&L!r2 | Y24 | same_period | Operation!AB14 | Operation!AB14 |
| P&L!AD11 | P&L\|11\|P&L!r2 | Y25 | same_period | -Operation!AC21 | Operation!AC21 |
| P&L!AD13 | P&L\|13\|P&L!r2 | Y25 | aggregation | SUM(AD9:AD12) | P&L!AD9:AD12 |
| P&L!AD15 | P&L\|15\|P&L!r2 | Y25 | same_period | Amortization!AC13 | Amortization!AC13 |
| P&L!AD17 | P&L\|17\|P&L!r2 | Y25 | aggregation | SUM(AD13:AD16) | P&L!AD13:AD16 |
| P&L!AD19 | P&L\|19\|P&L!r2 | Y25 | same_period | Debt!AD14 | Debt!AD14 |
| P&L!AD21 | P&L\|21\|P&L!r2 | Y25 | aggregation | SUM(AD17:AD20) | P&L!AD17:AD20 |
| P&L!AD23 | P&L\|23\|P&L!r2 | Y25 | conditional | IF(AD21<0,0,-'Input Assumptions'!$D$44*'P&L'!AD21) | P&L!AD21, Input Assumptions!D44 |
| P&L!AD25 | P&L\|25\|P&L!r2 | Y25 | aggregation | SUM(AD21:AD24) | P&L!AD21:AD24 |
| P&L!AD9 | P&L\|9\|P&L!r2 | Y25 | same_period | Operation!AC14 | Operation!AC14 |
| P&L!AE11 | P&L\|11\|P&L!r2 | Y26 | same_period | -Operation!AD21 | Operation!AD21 |
| P&L!AE13 | P&L\|13\|P&L!r2 | Y26 | aggregation | SUM(AE9:AE12) | P&L!AE9:AE12 |
| P&L!AE15 | P&L\|15\|P&L!r2 | Y26 | same_period | Amortization!AD13 | Amortization!AD13 |
| P&L!AE17 | P&L\|17\|P&L!r2 | Y26 | aggregation | SUM(AE13:AE16) | P&L!AE13:AE16 |
| P&L!AE19 | P&L\|19\|P&L!r2 | Y26 | same_period | Debt!AE14 | Debt!AE14 |
| P&L!AE21 | P&L\|21\|P&L!r2 | Y26 | aggregation | SUM(AE17:AE20) | P&L!AE17:AE20 |
| P&L!AE23 | P&L\|23\|P&L!r2 | Y26 | conditional | IF(AE21<0,0,-'Input Assumptions'!$D$44*'P&L'!AE21) | P&L!AE21, Input Assumptions!D44 |
| P&L!AE25 | P&L\|25\|P&L!r2 | Y26 | aggregation | SUM(AE21:AE24) | P&L!AE21:AE24 |
| P&L!AE9 | P&L\|9\|P&L!r2 | Y26 | same_period | Operation!AD14 | Operation!AD14 |
| P&L!AF11 | P&L\|11\|P&L!r2 | Y27 | same_period | -Operation!AE21 | Operation!AE21 |
| P&L!AF13 | P&L\|13\|P&L!r2 | Y27 | aggregation | SUM(AF9:AF12) | P&L!AF9:AF12 |
| P&L!AF15 | P&L\|15\|P&L!r2 | Y27 | same_period | Amortization!AE13 | Amortization!AE13 |
| P&L!AF17 | P&L\|17\|P&L!r2 | Y27 | aggregation | SUM(AF13:AF16) | P&L!AF13:AF16 |
| P&L!AF19 | P&L\|19\|P&L!r2 | Y27 | same_period | Debt!AF14 | Debt!AF14 |
| P&L!AF21 | P&L\|21\|P&L!r2 | Y27 | aggregation | SUM(AF17:AF20) | P&L!AF17:AF20 |
| P&L!AF23 | P&L\|23\|P&L!r2 | Y27 | conditional | IF(AF21<0,0,-'Input Assumptions'!$D$44*'P&L'!AF21) | P&L!AF21, Input Assumptions!D44 |
| P&L!AF25 | P&L\|25\|P&L!r2 | Y27 | aggregation | SUM(AF21:AF24) | P&L!AF21:AF24 |
| P&L!AF9 | P&L\|9\|P&L!r2 | Y27 | same_period | Operation!AE14 | Operation!AE14 |
| P&L!AG11 | P&L\|11\|P&L!r2 | Y28 | same_period | -Operation!AF21 | Operation!AF21 |
| P&L!AG13 | P&L\|13\|P&L!r2 | Y28 | aggregation | SUM(AG9:AG12) | P&L!AG9:AG12 |
| P&L!AG15 | P&L\|15\|P&L!r2 | Y28 | same_period | Amortization!AF13 | Amortization!AF13 |
| P&L!AG17 | P&L\|17\|P&L!r2 | Y28 | aggregation | SUM(AG13:AG16) | P&L!AG13:AG16 |
| P&L!AG19 | P&L\|19\|P&L!r2 | Y28 | same_period | Debt!AG14 | Debt!AG14 |
| P&L!AG21 | P&L\|21\|P&L!r2 | Y28 | aggregation | SUM(AG17:AG20) | P&L!AG17:AG20 |
| P&L!AG23 | P&L\|23\|P&L!r2 | Y28 | conditional | IF(AG21<0,0,-'Input Assumptions'!$D$44*'P&L'!AG21) | P&L!AG21, Input Assumptions!D44 |
| P&L!AG25 | P&L\|25\|P&L!r2 | Y28 | aggregation | SUM(AG21:AG24) | P&L!AG21:AG24 |
| P&L!AG9 | P&L\|9\|P&L!r2 | Y28 | same_period | Operation!AF14 | Operation!AF14 |
| P&L!AH11 | P&L\|11\|P&L!r2 | Y29 | same_period | -Operation!AG21 | Operation!AG21 |
| P&L!AH13 | P&L\|13\|P&L!r2 | Y29 | aggregation | SUM(AH9:AH12) | P&L!AH9:AH12 |
| P&L!AH15 | P&L\|15\|P&L!r2 | Y29 | same_period | Amortization!AG13 | Amortization!AG13 |
| P&L!AH17 | P&L\|17\|P&L!r2 | Y29 | aggregation | SUM(AH13:AH16) | P&L!AH13:AH16 |
| P&L!AH19 | P&L\|19\|P&L!r2 | Y29 | same_period | Debt!AH14 | Debt!AH14 |
| P&L!AH21 | P&L\|21\|P&L!r2 | Y29 | aggregation | SUM(AH17:AH20) | P&L!AH17:AH20 |
| P&L!AH23 | P&L\|23\|P&L!r2 | Y29 | conditional | IF(AH21<0,0,-'Input Assumptions'!$D$44*'P&L'!AH21) | P&L!AH21, Input Assumptions!D44 |
| P&L!AH25 | P&L\|25\|P&L!r2 | Y29 | aggregation | SUM(AH21:AH24) | P&L!AH21:AH24 |
| P&L!AH9 | P&L\|9\|P&L!r2 | Y29 | same_period | Operation!AG14 | Operation!AG14 |
| P&L!AI11 | P&L\|11\|P&L!r2 | Y30 | same_period | -Operation!AH21 | Operation!AH21 |
| P&L!AI13 | P&L\|13\|P&L!r2 | Y30 | aggregation | SUM(AI9:AI12) | P&L!AI9:AI12 |
| P&L!AI15 | P&L\|15\|P&L!r2 | Y30 | same_period | Amortization!AH13 | Amortization!AH13 |
| P&L!AI17 | P&L\|17\|P&L!r2 | Y30 | aggregation | SUM(AI13:AI16) | P&L!AI13:AI16 |
| P&L!AI19 | P&L\|19\|P&L!r2 | Y30 | same_period | Debt!AI14 | Debt!AI14 |
| P&L!AI21 | P&L\|21\|P&L!r2 | Y30 | aggregation | SUM(AI17:AI20) | P&L!AI17:AI20 |
| P&L!AI23 | P&L\|23\|P&L!r2 | Y30 | conditional | IF(AI21<0,0,-'Input Assumptions'!$D$44*'P&L'!AI21) | P&L!AI21, Input Assumptions!D44 |
| P&L!AI25 | P&L\|25\|P&L!r2 | Y30 | aggregation | SUM(AI21:AI24) | P&L!AI21:AI24 |
| P&L!AI9 | P&L\|9\|P&L!r2 | Y30 | same_period | Operation!AH14 | Operation!AH14 |
| P&L!AJ11 | P&L\|11\|P&L!r2 | Y31 | same_period | -Operation!AI21 | Operation!AI21 |
| P&L!AJ13 | P&L\|13\|P&L!r2 | Y31 | aggregation | SUM(AJ9:AJ12) | P&L!AJ9:AJ12 |
| P&L!AJ15 | P&L\|15\|P&L!r2 | Y31 | same_period | Amortization!AI13 | Amortization!AI13 |
| P&L!AJ17 | P&L\|17\|P&L!r2 | Y31 | aggregation | SUM(AJ13:AJ16) | P&L!AJ13:AJ16 |
| P&L!AJ19 | P&L\|19\|P&L!r2 | Y31 | same_period | Debt!AJ14 | Debt!AJ14 |
| P&L!AJ21 | P&L\|21\|P&L!r2 | Y31 | aggregation | SUM(AJ17:AJ20) | P&L!AJ17:AJ20 |
| P&L!AJ23 | P&L\|23\|P&L!r2 | Y31 | conditional | IF(AJ21<0,0,-'Input Assumptions'!$D$44*'P&L'!AJ21) | P&L!AJ21, Input Assumptions!D44 |
| P&L!AJ25 | P&L\|25\|P&L!r2 | Y31 | aggregation | SUM(AJ21:AJ24) | P&L!AJ21:AJ24 |
| P&L!AJ9 | P&L\|9\|P&L!r2 | Y31 | same_period | Operation!AI14 | Operation!AI14 |
| P&L!AK11 | P&L\|11\|P&L!r2 | Y32 | same_period | -Operation!AJ21 | Operation!AJ21 |
| P&L!AK13 | P&L\|13\|P&L!r2 | Y32 | aggregation | SUM(AK9:AK12) | P&L!AK9:AK12 |
| P&L!AK15 | P&L\|15\|P&L!r2 | Y32 | same_period | Amortization!AJ13 | Amortization!AJ13 |
| P&L!AK17 | P&L\|17\|P&L!r2 | Y32 | aggregation | SUM(AK13:AK16) | P&L!AK13:AK16 |
| P&L!AK19 | P&L\|19\|P&L!r2 | Y32 | same_period | Debt!AK14 | Debt!AK14 |
| P&L!AK21 | P&L\|21\|P&L!r2 | Y32 | aggregation | SUM(AK17:AK20) | P&L!AK17:AK20 |
| P&L!AK23 | P&L\|23\|P&L!r2 | Y32 | conditional | IF(AK21<0,0,-'Input Assumptions'!$D$44*'P&L'!AK21) | P&L!AK21, Input Assumptions!D44 |
| P&L!AK25 | P&L\|25\|P&L!r2 | Y32 | aggregation | SUM(AK21:AK24) | P&L!AK21:AK24 |
| P&L!AK9 | P&L\|9\|P&L!r2 | Y32 | same_period | Operation!AJ14 | Operation!AJ14 |
| P&L!AL11 | P&L\|11\|P&L!r2 | Y33 | same_period | -Operation!AK21 | Operation!AK21 |
| P&L!AL13 | P&L\|13\|P&L!r2 | Y33 | aggregation | SUM(AL9:AL12) | P&L!AL9:AL12 |
| P&L!AL15 | P&L\|15\|P&L!r2 | Y33 | same_period | Amortization!AK13 | Amortization!AK13 |
| P&L!AL17 | P&L\|17\|P&L!r2 | Y33 | aggregation | SUM(AL13:AL16) | P&L!AL13:AL16 |
| P&L!AL19 | P&L\|19\|P&L!r2 | Y33 | same_period | Debt!AL14 | Debt!AL14 |
| P&L!AL21 | P&L\|21\|P&L!r2 | Y33 | aggregation | SUM(AL17:AL20) | P&L!AL17:AL20 |
| P&L!AL23 | P&L\|23\|P&L!r2 | Y33 | conditional | IF(AL21<0,0,-'Input Assumptions'!$D$44*'P&L'!AL21) | P&L!AL21, Input Assumptions!D44 |
| P&L!AL25 | P&L\|25\|P&L!r2 | Y33 | aggregation | SUM(AL21:AL24) | P&L!AL21:AL24 |
| P&L!AL9 | P&L\|9\|P&L!r2 | Y33 | same_period | Operation!AK14 | Operation!AK14 |
| P&L!AM11 | P&L\|11\|P&L!r2 | Y34 | same_period | -Operation!AL21 | Operation!AL21 |
| P&L!AM13 | P&L\|13\|P&L!r2 | Y34 | aggregation | SUM(AM9:AM12) | P&L!AM9:AM12 |
| P&L!AM15 | P&L\|15\|P&L!r2 | Y34 | same_period | Amortization!AL13 | Amortization!AL13 |
| P&L!AM17 | P&L\|17\|P&L!r2 | Y34 | aggregation | SUM(AM13:AM16) | P&L!AM13:AM16 |
| P&L!AM19 | P&L\|19\|P&L!r2 | Y34 | same_period | Debt!AM14 | Debt!AM14 |
| P&L!AM21 | P&L\|21\|P&L!r2 | Y34 | aggregation | SUM(AM17:AM20) | P&L!AM17:AM20 |
| P&L!AM23 | P&L\|23\|P&L!r2 | Y34 | conditional | IF(AM21<0,0,-'Input Assumptions'!$D$44*'P&L'!AM21) | P&L!AM21, Input Assumptions!D44 |
| P&L!AM25 | P&L\|25\|P&L!r2 | Y34 | aggregation | SUM(AM21:AM24) | P&L!AM21:AM24 |
| P&L!AM9 | P&L\|9\|P&L!r2 | Y34 | same_period | Operation!AL14 | Operation!AL14 |
| P&L!AN11 | P&L\|11\|P&L!r2 | Y35 | same_period | -Operation!AM21 | Operation!AM21 |
| P&L!AN13 | P&L\|13\|P&L!r2 | Y35 | aggregation | SUM(AN9:AN12) | P&L!AN9:AN12 |
| P&L!AN15 | P&L\|15\|P&L!r2 | Y35 | same_period | Amortization!AM13 | Amortization!AM13 |
| P&L!AN17 | P&L\|17\|P&L!r2 | Y35 | aggregation | SUM(AN13:AN16) | P&L!AN13:AN16 |
| P&L!AN19 | P&L\|19\|P&L!r2 | Y35 | same_period | Debt!AN14 | Debt!AN14 |
| P&L!AN21 | P&L\|21\|P&L!r2 | Y35 | aggregation | SUM(AN17:AN20) | P&L!AN17:AN20 |
| P&L!AN23 | P&L\|23\|P&L!r2 | Y35 | conditional | IF(AN21<0,0,-'Input Assumptions'!$D$44*'P&L'!AN21) | P&L!AN21, Input Assumptions!D44 |
| P&L!AN25 | P&L\|25\|P&L!r2 | Y35 | aggregation | SUM(AN21:AN24) | P&L!AN21:AN24 |
| P&L!AN9 | P&L\|9\|P&L!r2 | Y35 | same_period | Operation!AM14 | Operation!AM14 |
| P&L!AO11 | P&L\|11\|P&L!r2 | Y36 | same_period | -Operation!AN21 | Operation!AN21 |
| P&L!AO13 | P&L\|13\|P&L!r2 | Y36 | aggregation | SUM(AO9:AO12) | P&L!AO9:AO12 |
| P&L!AO15 | P&L\|15\|P&L!r2 | Y36 | same_period | Amortization!AN13 | Amortization!AN13 |
| P&L!AO17 | P&L\|17\|P&L!r2 | Y36 | aggregation | SUM(AO13:AO16) | P&L!AO13:AO16 |
| P&L!AO19 | P&L\|19\|P&L!r2 | Y36 | same_period | Debt!AO14 | Debt!AO14 |
| P&L!AO21 | P&L\|21\|P&L!r2 | Y36 | aggregation | SUM(AO17:AO20) | P&L!AO17:AO20 |
| P&L!AO23 | P&L\|23\|P&L!r2 | Y36 | conditional | IF(AO21<0,0,-'Input Assumptions'!$D$44*'P&L'!AO21) | P&L!AO21, Input Assumptions!D44 |
| P&L!AO25 | P&L\|25\|P&L!r2 | Y36 | aggregation | SUM(AO21:AO24) | P&L!AO21:AO24 |
| P&L!AO9 | P&L\|9\|P&L!r2 | Y36 | same_period | Operation!AN14 | Operation!AN14 |
| P&L!AP11 | P&L\|11\|P&L!r2 | Y37 | same_period | -Operation!AO21 | Operation!AO21 |
| P&L!AP13 | P&L\|13\|P&L!r2 | Y37 | aggregation | SUM(AP9:AP12) | P&L!AP9:AP12 |
| P&L!AP15 | P&L\|15\|P&L!r2 | Y37 | same_period | Amortization!AO13 | Amortization!AO13 |
| P&L!AP17 | P&L\|17\|P&L!r2 | Y37 | aggregation | SUM(AP13:AP16) | P&L!AP13:AP16 |
| P&L!AP19 | P&L\|19\|P&L!r2 | Y37 | same_period | Debt!AP14 | Debt!AP14 |
| P&L!AP21 | P&L\|21\|P&L!r2 | Y37 | aggregation | SUM(AP17:AP20) | P&L!AP17:AP20 |
| P&L!AP23 | P&L\|23\|P&L!r2 | Y37 | conditional | IF(AP21<0,0,-'Input Assumptions'!$D$44*'P&L'!AP21) | P&L!AP21, Input Assumptions!D44 |
| P&L!AP25 | P&L\|25\|P&L!r2 | Y37 | aggregation | SUM(AP21:AP24) | P&L!AP21:AP24 |
| P&L!AP9 | P&L\|9\|P&L!r2 | Y37 | same_period | Operation!AO14 | Operation!AO14 |
| P&L!AQ11 | P&L\|11\|P&L!r2 | Y38 | same_period | -Operation!AP21 | Operation!AP21 |
| P&L!AQ13 | P&L\|13\|P&L!r2 | Y38 | aggregation | SUM(AQ9:AQ12) | P&L!AQ9:AQ12 |
| P&L!AQ15 | P&L\|15\|P&L!r2 | Y38 | same_period | Amortization!AP13 | Amortization!AP13 |
| P&L!AQ17 | P&L\|17\|P&L!r2 | Y38 | aggregation | SUM(AQ13:AQ16) | P&L!AQ13:AQ16 |
| P&L!AQ19 | P&L\|19\|P&L!r2 | Y38 | same_period | Debt!AQ14 | Debt!AQ14 |
| P&L!AQ21 | P&L\|21\|P&L!r2 | Y38 | aggregation | SUM(AQ17:AQ20) | P&L!AQ17:AQ20 |
| P&L!AQ23 | P&L\|23\|P&L!r2 | Y38 | conditional | IF(AQ21<0,0,-'Input Assumptions'!$D$44*'P&L'!AQ21) | P&L!AQ21, Input Assumptions!D44 |
| P&L!AQ25 | P&L\|25\|P&L!r2 | Y38 | aggregation | SUM(AQ21:AQ24) | P&L!AQ21:AQ24 |
| P&L!AQ9 | P&L\|9\|P&L!r2 | Y38 | same_period | Operation!AP14 | Operation!AP14 |
| P&L!AR11 | P&L\|11\|P&L!r2 | Y39 | same_period | -Operation!AQ21 | Operation!AQ21 |
| P&L!AR13 | P&L\|13\|P&L!r2 | Y39 | aggregation | SUM(AR9:AR12) | P&L!AR9:AR12 |
| P&L!AR15 | P&L\|15\|P&L!r2 | Y39 | same_period | Amortization!AQ13 | Amortization!AQ13 |
| P&L!AR17 | P&L\|17\|P&L!r2 | Y39 | aggregation | SUM(AR13:AR16) | P&L!AR13:AR16 |
| P&L!AR19 | P&L\|19\|P&L!r2 | Y39 | same_period | Debt!AR14 | Debt!AR14 |
| P&L!AR21 | P&L\|21\|P&L!r2 | Y39 | aggregation | SUM(AR17:AR20) | P&L!AR17:AR20 |
| P&L!AR23 | P&L\|23\|P&L!r2 | Y39 | conditional | IF(AR21<0,0,-'Input Assumptions'!$D$44*'P&L'!AR21) | P&L!AR21, Input Assumptions!D44 |
| P&L!AR25 | P&L\|25\|P&L!r2 | Y39 | aggregation | SUM(AR21:AR24) | P&L!AR21:AR24 |
| P&L!AR9 | P&L\|9\|P&L!r2 | Y39 | same_period | Operation!AQ14 | Operation!AQ14 |
| P&L!AS11 | P&L\|11\|P&L!r2 | Y40 | same_period | -Operation!AR21 | Operation!AR21 |
| P&L!AS13 | P&L\|13\|P&L!r2 | Y40 | aggregation | SUM(AS9:AS12) | P&L!AS9:AS12 |
| P&L!AS15 | P&L\|15\|P&L!r2 | Y40 | same_period | Amortization!AR13 | Amortization!AR13 |
| P&L!AS17 | P&L\|17\|P&L!r2 | Y40 | aggregation | SUM(AS13:AS16) | P&L!AS13:AS16 |
| P&L!AS19 | P&L\|19\|P&L!r2 | Y40 | same_period | Debt!AS14 | Debt!AS14 |
| P&L!AS21 | P&L\|21\|P&L!r2 | Y40 | aggregation | SUM(AS17:AS20) | P&L!AS17:AS20 |
| P&L!AS23 | P&L\|23\|P&L!r2 | Y40 | conditional | IF(AS21<0,0,-'Input Assumptions'!$D$44*'P&L'!AS21) | P&L!AS21, Input Assumptions!D44 |
| P&L!AS25 | P&L\|25\|P&L!r2 | Y40 | aggregation | SUM(AS21:AS24) | P&L!AS21:AS24 |
| P&L!AS9 | P&L\|9\|P&L!r2 | Y40 | same_period | Operation!AR14 | Operation!AR14 |
| P&L!F11 | P&L\|11\|P&L!r2 | Y1 | same_period | -Operation!E21 | Operation!E21 |
| P&L!F13 | P&L\|13\|P&L!r2 | Y1 | aggregation | SUM(F9:F12) | P&L!F9:F12 |
| P&L!F15 | P&L\|15\|P&L!r2 | Y1 | same_period | Amortization!E13 | Amortization!E13 |
| P&L!F17 | P&L\|17\|P&L!r2 | Y1 | aggregation | SUM(F13:F16) | P&L!F13:F16 |
| P&L!F19 | P&L\|19\|P&L!r2 | Y1 | same_period | Debt!F14 | Debt!F14 |
| P&L!F21 | P&L\|21\|P&L!r2 | Y1 | aggregation | SUM(F17:F20) | P&L!F17:F20 |
| P&L!F23 | P&L\|23\|P&L!r2 | Y1 | conditional | IF(F21<0,0,-'Input Assumptions'!$D$44*'P&L'!F21) | P&L!F21, Input Assumptions!D44 |
| P&L!F25 | P&L\|25\|P&L!r2 | Y1 | aggregation | SUM(F21:F24) | P&L!F21:F24 |
| P&L!F9 | P&L\|9\|P&L!r2 | Y1 | same_period | Operation!E14 | Operation!E14 |
| P&L!G11 | P&L\|11\|P&L!r2 | Y2 | same_period | -Operation!F21 | Operation!F21 |
| P&L!G13 | P&L\|13\|P&L!r2 | Y2 | aggregation | SUM(G9:G12) | P&L!G9:G12 |
| P&L!G15 | P&L\|15\|P&L!r2 | Y2 | same_period | Amortization!F13 | Amortization!F13 |
| P&L!G17 | P&L\|17\|P&L!r2 | Y2 | aggregation | SUM(G13:G16) | P&L!G13:G16 |
| P&L!G19 | P&L\|19\|P&L!r2 | Y2 | same_period | Debt!G14 | Debt!G14 |
| P&L!G21 | P&L\|21\|P&L!r2 | Y2 | aggregation | SUM(G17:G20) | P&L!G17:G20 |
| P&L!G23 | P&L\|23\|P&L!r2 | Y2 | conditional | IF(G21<0,0,-'Input Assumptions'!$D$44*'P&L'!G21) | P&L!G21, Input Assumptions!D44 |
| P&L!G25 | P&L\|25\|P&L!r2 | Y2 | aggregation | SUM(G21:G24) | P&L!G21:G24 |
| P&L!G9 | P&L\|9\|P&L!r2 | Y2 | same_period | Operation!F14 | Operation!F14 |
| P&L!H11 | P&L\|11\|P&L!r2 | Y3 | same_period | -Operation!G21 | Operation!G21 |
| P&L!H13 | P&L\|13\|P&L!r2 | Y3 | aggregation | SUM(H9:H12) | P&L!H9:H12 |
| P&L!H15 | P&L\|15\|P&L!r2 | Y3 | same_period | Amortization!G13 | Amortization!G13 |
| P&L!H17 | P&L\|17\|P&L!r2 | Y3 | aggregation | SUM(H13:H16) | P&L!H13:H16 |
| P&L!H19 | P&L\|19\|P&L!r2 | Y3 | same_period | Debt!H14 | Debt!H14 |
| P&L!H21 | P&L\|21\|P&L!r2 | Y3 | aggregation | SUM(H17:H20) | P&L!H17:H20 |
| P&L!H23 | P&L\|23\|P&L!r2 | Y3 | conditional | IF(H21<0,0,-'Input Assumptions'!$D$44*'P&L'!H21) | P&L!H21, Input Assumptions!D44 |
| P&L!H25 | P&L\|25\|P&L!r2 | Y3 | aggregation | SUM(H21:H24) | P&L!H21:H24 |
| P&L!H9 | P&L\|9\|P&L!r2 | Y3 | same_period | Operation!G14 | Operation!G14 |
| P&L!I11 | P&L\|11\|P&L!r2 | Y4 | same_period | -Operation!H21 | Operation!H21 |
| P&L!I13 | P&L\|13\|P&L!r2 | Y4 | aggregation | SUM(I9:I12) | P&L!I9:I12 |
| P&L!I15 | P&L\|15\|P&L!r2 | Y4 | same_period | Amortization!H13 | Amortization!H13 |
| P&L!I17 | P&L\|17\|P&L!r2 | Y4 | aggregation | SUM(I13:I16) | P&L!I13:I16 |
| P&L!I19 | P&L\|19\|P&L!r2 | Y4 | same_period | Debt!I14 | Debt!I14 |
| P&L!I21 | P&L\|21\|P&L!r2 | Y4 | aggregation | SUM(I17:I20) | P&L!I17:I20 |
| P&L!I23 | P&L\|23\|P&L!r2 | Y4 | conditional | IF(I21<0,0,-'Input Assumptions'!$D$44*'P&L'!I21) | P&L!I21, Input Assumptions!D44 |
| P&L!I25 | P&L\|25\|P&L!r2 | Y4 | aggregation | SUM(I21:I24) | P&L!I21:I24 |
| P&L!I9 | P&L\|9\|P&L!r2 | Y4 | same_period | Operation!H14 | Operation!H14 |
| P&L!J11 | P&L\|11\|P&L!r2 | Y5 | same_period | -Operation!I21 | Operation!I21 |
| P&L!J13 | P&L\|13\|P&L!r2 | Y5 | aggregation | SUM(J9:J12) | P&L!J9:J12 |
| P&L!J15 | P&L\|15\|P&L!r2 | Y5 | same_period | Amortization!I13 | Amortization!I13 |
| P&L!J17 | P&L\|17\|P&L!r2 | Y5 | aggregation | SUM(J13:J16) | P&L!J13:J16 |
| P&L!J19 | P&L\|19\|P&L!r2 | Y5 | same_period | Debt!J14 | Debt!J14 |
| P&L!J21 | P&L\|21\|P&L!r2 | Y5 | aggregation | SUM(J17:J20) | P&L!J17:J20 |
| P&L!J23 | P&L\|23\|P&L!r2 | Y5 | conditional | IF(J21<0,0,-'Input Assumptions'!$D$44*'P&L'!J21) | P&L!J21, Input Assumptions!D44 |
| P&L!J25 | P&L\|25\|P&L!r2 | Y5 | aggregation | SUM(J21:J24) | P&L!J21:J24 |
| P&L!J9 | P&L\|9\|P&L!r2 | Y5 | same_period | Operation!I14 | Operation!I14 |
| P&L!K11 | P&L\|11\|P&L!r2 | Y6 | same_period | -Operation!J21 | Operation!J21 |
| P&L!K13 | P&L\|13\|P&L!r2 | Y6 | aggregation | SUM(K9:K12) | P&L!K9:K12 |
| P&L!K15 | P&L\|15\|P&L!r2 | Y6 | same_period | Amortization!J13 | Amortization!J13 |
| P&L!K17 | P&L\|17\|P&L!r2 | Y6 | aggregation | SUM(K13:K16) | P&L!K13:K16 |
| P&L!K19 | P&L\|19\|P&L!r2 | Y6 | same_period | Debt!K14 | Debt!K14 |
| P&L!K21 | P&L\|21\|P&L!r2 | Y6 | aggregation | SUM(K17:K20) | P&L!K17:K20 |
| P&L!K23 | P&L\|23\|P&L!r2 | Y6 | conditional | IF(K21<0,0,-'Input Assumptions'!$D$44*'P&L'!K21) | P&L!K21, Input Assumptions!D44 |
| P&L!K25 | P&L\|25\|P&L!r2 | Y6 | aggregation | SUM(K21:K24) | P&L!K21:K24 |
| P&L!K9 | P&L\|9\|P&L!r2 | Y6 | same_period | Operation!J14 | Operation!J14 |
| P&L!L11 | P&L\|11\|P&L!r2 | Y7 | same_period | -Operation!K21 | Operation!K21 |
| P&L!L13 | P&L\|13\|P&L!r2 | Y7 | aggregation | SUM(L9:L12) | P&L!L9:L12 |
| P&L!L15 | P&L\|15\|P&L!r2 | Y7 | same_period | Amortization!K13 | Amortization!K13 |
| P&L!L17 | P&L\|17\|P&L!r2 | Y7 | aggregation | SUM(L13:L16) | P&L!L13:L16 |
| P&L!L19 | P&L\|19\|P&L!r2 | Y7 | same_period | Debt!L14 | Debt!L14 |
| P&L!L21 | P&L\|21\|P&L!r2 | Y7 | aggregation | SUM(L17:L20) | P&L!L17:L20 |
| P&L!L23 | P&L\|23\|P&L!r2 | Y7 | conditional | IF(L21<0,0,-'Input Assumptions'!$D$44*'P&L'!L21) | P&L!L21, Input Assumptions!D44 |
| P&L!L25 | P&L\|25\|P&L!r2 | Y7 | aggregation | SUM(L21:L24) | P&L!L21:L24 |
| P&L!L9 | P&L\|9\|P&L!r2 | Y7 | same_period | Operation!K14 | Operation!K14 |
| P&L!M11 | P&L\|11\|P&L!r2 | Y8 | same_period | -Operation!L21 | Operation!L21 |
| P&L!M13 | P&L\|13\|P&L!r2 | Y8 | aggregation | SUM(M9:M12) | P&L!M9:M12 |
| P&L!M15 | P&L\|15\|P&L!r2 | Y8 | same_period | Amortization!L13 | Amortization!L13 |
| P&L!M17 | P&L\|17\|P&L!r2 | Y8 | aggregation | SUM(M13:M16) | P&L!M13:M16 |
| P&L!M19 | P&L\|19\|P&L!r2 | Y8 | same_period | Debt!M14 | Debt!M14 |
| P&L!M21 | P&L\|21\|P&L!r2 | Y8 | aggregation | SUM(M17:M20) | P&L!M17:M20 |
| P&L!M23 | P&L\|23\|P&L!r2 | Y8 | conditional | IF(M21<0,0,-'Input Assumptions'!$D$44*'P&L'!M21) | P&L!M21, Input Assumptions!D44 |
| P&L!M25 | P&L\|25\|P&L!r2 | Y8 | aggregation | SUM(M21:M24) | P&L!M21:M24 |
| P&L!M9 | P&L\|9\|P&L!r2 | Y8 | same_period | Operation!L14 | Operation!L14 |
| P&L!N11 | P&L\|11\|P&L!r2 | Y9 | same_period | -Operation!M21 | Operation!M21 |
| P&L!N13 | P&L\|13\|P&L!r2 | Y9 | aggregation | SUM(N9:N12) | P&L!N9:N12 |
| P&L!N15 | P&L\|15\|P&L!r2 | Y9 | same_period | Amortization!M13 | Amortization!M13 |
| P&L!N17 | P&L\|17\|P&L!r2 | Y9 | aggregation | SUM(N13:N16) | P&L!N13:N16 |
| P&L!N19 | P&L\|19\|P&L!r2 | Y9 | same_period | Debt!N14 | Debt!N14 |
| P&L!N21 | P&L\|21\|P&L!r2 | Y9 | aggregation | SUM(N17:N20) | P&L!N17:N20 |
| P&L!N23 | P&L\|23\|P&L!r2 | Y9 | conditional | IF(N21<0,0,-'Input Assumptions'!$D$44*'P&L'!N21) | P&L!N21, Input Assumptions!D44 |
| P&L!N25 | P&L\|25\|P&L!r2 | Y9 | aggregation | SUM(N21:N24) | P&L!N21:N24 |
| P&L!N9 | P&L\|9\|P&L!r2 | Y9 | same_period | Operation!M14 | Operation!M14 |
| P&L!O11 | P&L\|11\|P&L!r2 | Y10 | same_period | -Operation!N21 | Operation!N21 |
| P&L!O13 | P&L\|13\|P&L!r2 | Y10 | aggregation | SUM(O9:O12) | P&L!O9:O12 |
| P&L!O15 | P&L\|15\|P&L!r2 | Y10 | same_period | Amortization!N13 | Amortization!N13 |
| P&L!O17 | P&L\|17\|P&L!r2 | Y10 | aggregation | SUM(O13:O16) | P&L!O13:O16 |
| P&L!O19 | P&L\|19\|P&L!r2 | Y10 | same_period | Debt!O14 | Debt!O14 |
| P&L!O21 | P&L\|21\|P&L!r2 | Y10 | aggregation | SUM(O17:O20) | P&L!O17:O20 |
| P&L!O23 | P&L\|23\|P&L!r2 | Y10 | conditional | IF(O21<0,0,-'Input Assumptions'!$D$44*'P&L'!O21) | P&L!O21, Input Assumptions!D44 |
| P&L!O25 | P&L\|25\|P&L!r2 | Y10 | aggregation | SUM(O21:O24) | P&L!O21:O24 |
| P&L!O9 | P&L\|9\|P&L!r2 | Y10 | same_period | Operation!N14 | Operation!N14 |
| P&L!P11 | P&L\|11\|P&L!r2 | Y11 | same_period | -Operation!O21 | Operation!O21 |
| P&L!P13 | P&L\|13\|P&L!r2 | Y11 | aggregation | SUM(P9:P12) | P&L!P9:P12 |
| P&L!P15 | P&L\|15\|P&L!r2 | Y11 | same_period | Amortization!O13 | Amortization!O13 |
| P&L!P17 | P&L\|17\|P&L!r2 | Y11 | aggregation | SUM(P13:P16) | P&L!P13:P16 |
| P&L!P19 | P&L\|19\|P&L!r2 | Y11 | same_period | Debt!P14 | Debt!P14 |
| P&L!P21 | P&L\|21\|P&L!r2 | Y11 | aggregation | SUM(P17:P20) | P&L!P17:P20 |
| P&L!P23 | P&L\|23\|P&L!r2 | Y11 | conditional | IF(P21<0,0,-'Input Assumptions'!$D$44*'P&L'!P21) | P&L!P21, Input Assumptions!D44 |
| P&L!P25 | P&L\|25\|P&L!r2 | Y11 | aggregation | SUM(P21:P24) | P&L!P21:P24 |
| P&L!P9 | P&L\|9\|P&L!r2 | Y11 | same_period | Operation!O14 | Operation!O14 |
| P&L!Q11 | P&L\|11\|P&L!r2 | Y12 | same_period | -Operation!P21 | Operation!P21 |
| P&L!Q13 | P&L\|13\|P&L!r2 | Y12 | aggregation | SUM(Q9:Q12) | P&L!Q9:Q12 |
| P&L!Q15 | P&L\|15\|P&L!r2 | Y12 | same_period | Amortization!P13 | Amortization!P13 |
| P&L!Q17 | P&L\|17\|P&L!r2 | Y12 | aggregation | SUM(Q13:Q16) | P&L!Q13:Q16 |
| P&L!Q19 | P&L\|19\|P&L!r2 | Y12 | same_period | Debt!Q14 | Debt!Q14 |
| P&L!Q21 | P&L\|21\|P&L!r2 | Y12 | aggregation | SUM(Q17:Q20) | P&L!Q17:Q20 |
| P&L!Q23 | P&L\|23\|P&L!r2 | Y12 | conditional | IF(Q21<0,0,-'Input Assumptions'!$D$44*'P&L'!Q21) | P&L!Q21, Input Assumptions!D44 |
| P&L!Q25 | P&L\|25\|P&L!r2 | Y12 | aggregation | SUM(Q21:Q24) | P&L!Q21:Q24 |
| P&L!Q9 | P&L\|9\|P&L!r2 | Y12 | same_period | Operation!P14 | Operation!P14 |
| P&L!R11 | P&L\|11\|P&L!r2 | Y13 | same_period | -Operation!Q21 | Operation!Q21 |
| P&L!R13 | P&L\|13\|P&L!r2 | Y13 | aggregation | SUM(R9:R12) | P&L!R9:R12 |
| P&L!R15 | P&L\|15\|P&L!r2 | Y13 | same_period | Amortization!Q13 | Amortization!Q13 |
| P&L!R17 | P&L\|17\|P&L!r2 | Y13 | aggregation | SUM(R13:R16) | P&L!R13:R16 |
| P&L!R19 | P&L\|19\|P&L!r2 | Y13 | same_period | Debt!R14 | Debt!R14 |
| P&L!R21 | P&L\|21\|P&L!r2 | Y13 | aggregation | SUM(R17:R20) | P&L!R17:R20 |
| P&L!R23 | P&L\|23\|P&L!r2 | Y13 | conditional | IF(R21<0,0,-'Input Assumptions'!$D$44*'P&L'!R21) | P&L!R21, Input Assumptions!D44 |
| P&L!R25 | P&L\|25\|P&L!r2 | Y13 | aggregation | SUM(R21:R24) | P&L!R21:R24 |
| P&L!R9 | P&L\|9\|P&L!r2 | Y13 | same_period | Operation!Q14 | Operation!Q14 |
| P&L!S11 | P&L\|11\|P&L!r2 | Y14 | same_period | -Operation!R21 | Operation!R21 |
| P&L!S13 | P&L\|13\|P&L!r2 | Y14 | aggregation | SUM(S9:S12) | P&L!S9:S12 |
| P&L!S15 | P&L\|15\|P&L!r2 | Y14 | same_period | Amortization!R13 | Amortization!R13 |
| P&L!S17 | P&L\|17\|P&L!r2 | Y14 | aggregation | SUM(S13:S16) | P&L!S13:S16 |
| P&L!S19 | P&L\|19\|P&L!r2 | Y14 | same_period | Debt!S14 | Debt!S14 |
| P&L!S21 | P&L\|21\|P&L!r2 | Y14 | aggregation | SUM(S17:S20) | P&L!S17:S20 |
| P&L!S23 | P&L\|23\|P&L!r2 | Y14 | conditional | IF(S21<0,0,-'Input Assumptions'!$D$44*'P&L'!S21) | P&L!S21, Input Assumptions!D44 |
| P&L!S25 | P&L\|25\|P&L!r2 | Y14 | aggregation | SUM(S21:S24) | P&L!S21:S24 |
| P&L!S9 | P&L\|9\|P&L!r2 | Y14 | same_period | Operation!R14 | Operation!R14 |
| P&L!T11 | P&L\|11\|P&L!r2 | Y15 | same_period | -Operation!S21 | Operation!S21 |
| P&L!T13 | P&L\|13\|P&L!r2 | Y15 | aggregation | SUM(T9:T12) | P&L!T9:T12 |
| P&L!T15 | P&L\|15\|P&L!r2 | Y15 | same_period | Amortization!S13 | Amortization!S13 |
| P&L!T17 | P&L\|17\|P&L!r2 | Y15 | aggregation | SUM(T13:T16) | P&L!T13:T16 |
| P&L!T19 | P&L\|19\|P&L!r2 | Y15 | same_period | Debt!T14 | Debt!T14 |
| P&L!T21 | P&L\|21\|P&L!r2 | Y15 | aggregation | SUM(T17:T20) | P&L!T17:T20 |
| P&L!T23 | P&L\|23\|P&L!r2 | Y15 | conditional | IF(T21<0,0,-'Input Assumptions'!$D$44*'P&L'!T21) | P&L!T21, Input Assumptions!D44 |
| P&L!T25 | P&L\|25\|P&L!r2 | Y15 | aggregation | SUM(T21:T24) | P&L!T21:T24 |
| P&L!T9 | P&L\|9\|P&L!r2 | Y15 | same_period | Operation!S14 | Operation!S14 |
| P&L!U11 | P&L\|11\|P&L!r2 | Y16 | same_period | -Operation!T21 | Operation!T21 |
| P&L!U13 | P&L\|13\|P&L!r2 | Y16 | aggregation | SUM(U9:U12) | P&L!U9:U12 |
| P&L!U15 | P&L\|15\|P&L!r2 | Y16 | same_period | Amortization!T13 | Amortization!T13 |
| P&L!U17 | P&L\|17\|P&L!r2 | Y16 | aggregation | SUM(U13:U16) | P&L!U13:U16 |
| P&L!U19 | P&L\|19\|P&L!r2 | Y16 | same_period | Debt!U14 | Debt!U14 |
| P&L!U21 | P&L\|21\|P&L!r2 | Y16 | aggregation | SUM(U17:U20) | P&L!U17:U20 |
| P&L!U23 | P&L\|23\|P&L!r2 | Y16 | conditional | IF(U21<0,0,-'Input Assumptions'!$D$44*'P&L'!U21) | P&L!U21, Input Assumptions!D44 |
| P&L!U25 | P&L\|25\|P&L!r2 | Y16 | aggregation | SUM(U21:U24) | P&L!U21:U24 |
| P&L!U9 | P&L\|9\|P&L!r2 | Y16 | same_period | Operation!T14 | Operation!T14 |
| P&L!V11 | P&L\|11\|P&L!r2 | Y17 | same_period | -Operation!U21 | Operation!U21 |
| P&L!V13 | P&L\|13\|P&L!r2 | Y17 | aggregation | SUM(V9:V12) | P&L!V9:V12 |
| P&L!V15 | P&L\|15\|P&L!r2 | Y17 | same_period | Amortization!U13 | Amortization!U13 |
| P&L!V17 | P&L\|17\|P&L!r2 | Y17 | aggregation | SUM(V13:V16) | P&L!V13:V16 |
| P&L!V19 | P&L\|19\|P&L!r2 | Y17 | same_period | Debt!V14 | Debt!V14 |
| P&L!V21 | P&L\|21\|P&L!r2 | Y17 | aggregation | SUM(V17:V20) | P&L!V17:V20 |
| P&L!V23 | P&L\|23\|P&L!r2 | Y17 | conditional | IF(V21<0,0,-'Input Assumptions'!$D$44*'P&L'!V21) | P&L!V21, Input Assumptions!D44 |
| P&L!V25 | P&L\|25\|P&L!r2 | Y17 | aggregation | SUM(V21:V24) | P&L!V21:V24 |
| P&L!V9 | P&L\|9\|P&L!r2 | Y17 | same_period | Operation!U14 | Operation!U14 |
| P&L!W11 | P&L\|11\|P&L!r2 | Y18 | same_period | -Operation!V21 | Operation!V21 |
| P&L!W13 | P&L\|13\|P&L!r2 | Y18 | aggregation | SUM(W9:W12) | P&L!W9:W12 |
| P&L!W15 | P&L\|15\|P&L!r2 | Y18 | same_period | Amortization!V13 | Amortization!V13 |
| P&L!W17 | P&L\|17\|P&L!r2 | Y18 | aggregation | SUM(W13:W16) | P&L!W13:W16 |
| P&L!W19 | P&L\|19\|P&L!r2 | Y18 | same_period | Debt!W14 | Debt!W14 |
| P&L!W21 | P&L\|21\|P&L!r2 | Y18 | aggregation | SUM(W17:W20) | P&L!W17:W20 |
| P&L!W23 | P&L\|23\|P&L!r2 | Y18 | conditional | IF(W21<0,0,-'Input Assumptions'!$D$44*'P&L'!W21) | P&L!W21, Input Assumptions!D44 |
| P&L!W25 | P&L\|25\|P&L!r2 | Y18 | aggregation | SUM(W21:W24) | P&L!W21:W24 |
| P&L!W9 | P&L\|9\|P&L!r2 | Y18 | same_period | Operation!V14 | Operation!V14 |
| P&L!X11 | P&L\|11\|P&L!r2 | Y19 | same_period | -Operation!W21 | Operation!W21 |
| P&L!X13 | P&L\|13\|P&L!r2 | Y19 | aggregation | SUM(X9:X12) | P&L!X9:X12 |
| P&L!X15 | P&L\|15\|P&L!r2 | Y19 | same_period | Amortization!W13 | Amortization!W13 |
| P&L!X17 | P&L\|17\|P&L!r2 | Y19 | aggregation | SUM(X13:X16) | P&L!X13:X16 |
| P&L!X19 | P&L\|19\|P&L!r2 | Y19 | same_period | Debt!X14 | Debt!X14 |
| P&L!X21 | P&L\|21\|P&L!r2 | Y19 | aggregation | SUM(X17:X20) | P&L!X17:X20 |
| P&L!X23 | P&L\|23\|P&L!r2 | Y19 | conditional | IF(X21<0,0,-'Input Assumptions'!$D$44*'P&L'!X21) | P&L!X21, Input Assumptions!D44 |
| P&L!X25 | P&L\|25\|P&L!r2 | Y19 | aggregation | SUM(X21:X24) | P&L!X21:X24 |
| P&L!X9 | P&L\|9\|P&L!r2 | Y19 | same_period | Operation!W14 | Operation!W14 |
| P&L!Y11 | P&L\|11\|P&L!r2 | Y20 | same_period | -Operation!X21 | Operation!X21 |
| P&L!Y13 | P&L\|13\|P&L!r2 | Y20 | aggregation | SUM(Y9:Y12) | P&L!Y9:Y12 |
| P&L!Y15 | P&L\|15\|P&L!r2 | Y20 | same_period | Amortization!X13 | Amortization!X13 |
| P&L!Y17 | P&L\|17\|P&L!r2 | Y20 | aggregation | SUM(Y13:Y16) | P&L!Y13:Y16 |
| P&L!Y19 | P&L\|19\|P&L!r2 | Y20 | same_period | Debt!Y14 | Debt!Y14 |
| P&L!Y21 | P&L\|21\|P&L!r2 | Y20 | aggregation | SUM(Y17:Y20) | P&L!Y17:Y20 |
| P&L!Y23 | P&L\|23\|P&L!r2 | Y20 | conditional | IF(Y21<0,0,-'Input Assumptions'!$D$44*'P&L'!Y21) | P&L!Y21, Input Assumptions!D44 |
| P&L!Y25 | P&L\|25\|P&L!r2 | Y20 | aggregation | SUM(Y21:Y24) | P&L!Y21:Y24 |
| P&L!Y9 | P&L\|9\|P&L!r2 | Y20 | same_period | Operation!X14 | Operation!X14 |
| P&L!Z11 | P&L\|11\|P&L!r2 | Y21 | same_period | -Operation!Y21 | Operation!Y21 |
| P&L!Z13 | P&L\|13\|P&L!r2 | Y21 | aggregation | SUM(Z9:Z12) | P&L!Z9:Z12 |
| P&L!Z15 | P&L\|15\|P&L!r2 | Y21 | same_period | Amortization!Y13 | Amortization!Y13 |
| P&L!Z17 | P&L\|17\|P&L!r2 | Y21 | aggregation | SUM(Z13:Z16) | P&L!Z13:Z16 |
| P&L!Z19 | P&L\|19\|P&L!r2 | Y21 | same_period | Debt!Z14 | Debt!Z14 |
| P&L!Z21 | P&L\|21\|P&L!r2 | Y21 | aggregation | SUM(Z17:Z20) | P&L!Z17:Z20 |
| P&L!Z23 | P&L\|23\|P&L!r2 | Y21 | conditional | IF(Z21<0,0,-'Input Assumptions'!$D$44*'P&L'!Z21) | P&L!Z21, Input Assumptions!D44 |
| P&L!Z25 | P&L\|25\|P&L!r2 | Y21 | aggregation | SUM(Z21:Z24) | P&L!Z21:Z24 |
| P&L!Z9 | P&L\|9\|P&L!r2 | Y21 | same_period | Operation!Y14 | Operation!Y14 |
| Ratios!AA10 | Ratios\|10\|Ratios!r3 | Y22 | same_period | -Construction!Z14 | Construction!Z14 |
| Ratios!AA11 | Ratios\|11\|Ratios!r3 | Y22 | same_period | -Construction!Z15 | Construction!Z15 |
| Ratios!AA12 | Ratios\|12\|Ratios!r3 | Y22 | aggregation | SUM(AA8:AA11) | Ratios!AA8:AA11 |
| Ratios!AA14 | Ratios\|14\|Ratios!r3 | Y22 | same_period | Operation!Z14 | Operation!Z14 |
| Ratios!AA15 | Ratios\|15\|Ratios!r3 | Y22 | same_period | -Operation!Z21 | Operation!Z21 |
| Ratios!AA16 | Ratios\|16\|Ratios!r3 | Y22 | same_period | 'P&L'!AA23 | P&L!AA23 |
| Ratios!AA17 | Ratios\|17\|Ratios!r3 | Y22 | aggregation | SUM(AA12:AA16) | Ratios!AA12:AA16 |
| Ratios!AA24 | Ratios\|24\|Ratios!r3 | Y22 | same_period | -Construction!Z26 | Construction!Z26 |
| Ratios!AA25 | Ratios\|25\|Ratios!r3 | Y22 | same_period | -CFS!AA21 | CFS!AA21 |
| Ratios!AA27 | Ratios\|27\|Ratios!r3 | Y22 | aggregation | SUM(AA24:AA26) | Ratios!AA24:AA26 |
| Ratios!AA8 | Ratios\|8\|Ratios!r3 | Y22 | same_period | -Construction!Z12 | Construction!Z12 |
| Ratios!AA9 | Ratios\|9\|Ratios!r3 | Y22 | same_period | -Construction!Z13 | Construction!Z13 |
| Ratios!AB10 | Ratios\|10\|Ratios!r3 | Y23 | same_period | -Construction!AA14 | Construction!AA14 |
| Ratios!AB11 | Ratios\|11\|Ratios!r3 | Y23 | same_period | -Construction!AA15 | Construction!AA15 |
| Ratios!AB12 | Ratios\|12\|Ratios!r3 | Y23 | aggregation | SUM(AB8:AB11) | Ratios!AB8:AB11 |
| Ratios!AB14 | Ratios\|14\|Ratios!r3 | Y23 | same_period | Operation!AA14 | Operation!AA14 |
| Ratios!AB15 | Ratios\|15\|Ratios!r3 | Y23 | same_period | -Operation!AA21 | Operation!AA21 |
| Ratios!AB16 | Ratios\|16\|Ratios!r3 | Y23 | same_period | 'P&L'!AB23 | P&L!AB23 |
| Ratios!AB17 | Ratios\|17\|Ratios!r3 | Y23 | aggregation | SUM(AB12:AB16) | Ratios!AB12:AB16 |
| Ratios!AB24 | Ratios\|24\|Ratios!r3 | Y23 | same_period | -Construction!AA26 | Construction!AA26 |
| Ratios!AB25 | Ratios\|25\|Ratios!r3 | Y23 | same_period | -CFS!AB21 | CFS!AB21 |
| Ratios!AB27 | Ratios\|27\|Ratios!r3 | Y23 | aggregation | SUM(AB24:AB26) | Ratios!AB24:AB26 |
| Ratios!AB8 | Ratios\|8\|Ratios!r3 | Y23 | same_period | -Construction!AA12 | Construction!AA12 |
| Ratios!AB9 | Ratios\|9\|Ratios!r3 | Y23 | same_period | -Construction!AA13 | Construction!AA13 |
| Ratios!AC10 | Ratios\|10\|Ratios!r3 | Y24 | same_period | -Construction!AB14 | Construction!AB14 |
| Ratios!AC11 | Ratios\|11\|Ratios!r3 | Y24 | same_period | -Construction!AB15 | Construction!AB15 |
| Ratios!AC12 | Ratios\|12\|Ratios!r3 | Y24 | aggregation | SUM(AC8:AC11) | Ratios!AC8:AC11 |
| Ratios!AC14 | Ratios\|14\|Ratios!r3 | Y24 | same_period | Operation!AB14 | Operation!AB14 |
| Ratios!AC15 | Ratios\|15\|Ratios!r3 | Y24 | same_period | -Operation!AB21 | Operation!AB21 |
| Ratios!AC16 | Ratios\|16\|Ratios!r3 | Y24 | same_period | 'P&L'!AC23 | P&L!AC23 |
| Ratios!AC17 | Ratios\|17\|Ratios!r3 | Y24 | aggregation | SUM(AC12:AC16) | Ratios!AC12:AC16 |
| Ratios!AC24 | Ratios\|24\|Ratios!r3 | Y24 | same_period | -Construction!AB26 | Construction!AB26 |
| Ratios!AC25 | Ratios\|25\|Ratios!r3 | Y24 | same_period | -CFS!AC21 | CFS!AC21 |
| Ratios!AC27 | Ratios\|27\|Ratios!r3 | Y24 | aggregation | SUM(AC24:AC26) | Ratios!AC24:AC26 |
| Ratios!AC8 | Ratios\|8\|Ratios!r3 | Y24 | same_period | -Construction!AB12 | Construction!AB12 |
| Ratios!AC9 | Ratios\|9\|Ratios!r3 | Y24 | same_period | -Construction!AB13 | Construction!AB13 |
| Ratios!AD10 | Ratios\|10\|Ratios!r3 | Y25 | same_period | -Construction!AC14 | Construction!AC14 |
| Ratios!AD11 | Ratios\|11\|Ratios!r3 | Y25 | same_period | -Construction!AC15 | Construction!AC15 |
| Ratios!AD12 | Ratios\|12\|Ratios!r3 | Y25 | aggregation | SUM(AD8:AD11) | Ratios!AD8:AD11 |
| Ratios!AD14 | Ratios\|14\|Ratios!r3 | Y25 | same_period | Operation!AC14 | Operation!AC14 |
| Ratios!AD15 | Ratios\|15\|Ratios!r3 | Y25 | same_period | -Operation!AC21 | Operation!AC21 |
| Ratios!AD16 | Ratios\|16\|Ratios!r3 | Y25 | same_period | 'P&L'!AD23 | P&L!AD23 |
| Ratios!AD17 | Ratios\|17\|Ratios!r3 | Y25 | aggregation | SUM(AD12:AD16) | Ratios!AD12:AD16 |
| Ratios!AD24 | Ratios\|24\|Ratios!r3 | Y25 | same_period | -Construction!AC26 | Construction!AC26 |
| Ratios!AD25 | Ratios\|25\|Ratios!r3 | Y25 | same_period | -CFS!AD21 | CFS!AD21 |
| Ratios!AD27 | Ratios\|27\|Ratios!r3 | Y25 | aggregation | SUM(AD24:AD26) | Ratios!AD24:AD26 |
| Ratios!AD8 | Ratios\|8\|Ratios!r3 | Y25 | same_period | -Construction!AC12 | Construction!AC12 |
| Ratios!AD9 | Ratios\|9\|Ratios!r3 | Y25 | same_period | -Construction!AC13 | Construction!AC13 |
| Ratios!AE10 | Ratios\|10\|Ratios!r3 | Y26 | same_period | -Construction!AD14 | Construction!AD14 |
| Ratios!AE11 | Ratios\|11\|Ratios!r3 | Y26 | same_period | -Construction!AD15 | Construction!AD15 |
| Ratios!AE12 | Ratios\|12\|Ratios!r3 | Y26 | aggregation | SUM(AE8:AE11) | Ratios!AE8:AE11 |
| Ratios!AE14 | Ratios\|14\|Ratios!r3 | Y26 | same_period | Operation!AD14 | Operation!AD14 |
| Ratios!AE15 | Ratios\|15\|Ratios!r3 | Y26 | same_period | -Operation!AD21 | Operation!AD21 |
| Ratios!AE16 | Ratios\|16\|Ratios!r3 | Y26 | same_period | 'P&L'!AE23 | P&L!AE23 |
| Ratios!AE17 | Ratios\|17\|Ratios!r3 | Y26 | aggregation | SUM(AE12:AE16) | Ratios!AE12:AE16 |
| Ratios!AE24 | Ratios\|24\|Ratios!r3 | Y26 | same_period | -Construction!AD26 | Construction!AD26 |
| Ratios!AE25 | Ratios\|25\|Ratios!r3 | Y26 | same_period | -CFS!AE21 | CFS!AE21 |
| Ratios!AE27 | Ratios\|27\|Ratios!r3 | Y26 | aggregation | SUM(AE24:AE26) | Ratios!AE24:AE26 |
| Ratios!AE8 | Ratios\|8\|Ratios!r3 | Y26 | same_period | -Construction!AD12 | Construction!AD12 |
| Ratios!AE9 | Ratios\|9\|Ratios!r3 | Y26 | same_period | -Construction!AD13 | Construction!AD13 |
| Ratios!AF10 | Ratios\|10\|Ratios!r3 | Y27 | same_period | -Construction!AE14 | Construction!AE14 |
| Ratios!AF11 | Ratios\|11\|Ratios!r3 | Y27 | same_period | -Construction!AE15 | Construction!AE15 |
| Ratios!AF12 | Ratios\|12\|Ratios!r3 | Y27 | aggregation | SUM(AF8:AF11) | Ratios!AF8:AF11 |
| Ratios!AF14 | Ratios\|14\|Ratios!r3 | Y27 | same_period | Operation!AE14 | Operation!AE14 |
| Ratios!AF15 | Ratios\|15\|Ratios!r3 | Y27 | same_period | -Operation!AE21 | Operation!AE21 |
| Ratios!AF16 | Ratios\|16\|Ratios!r3 | Y27 | same_period | 'P&L'!AF23 | P&L!AF23 |
| Ratios!AF17 | Ratios\|17\|Ratios!r3 | Y27 | aggregation | SUM(AF12:AF16) | Ratios!AF12:AF16 |
| Ratios!AF24 | Ratios\|24\|Ratios!r3 | Y27 | same_period | -Construction!AE26 | Construction!AE26 |
| Ratios!AF25 | Ratios\|25\|Ratios!r3 | Y27 | same_period | -CFS!AF21 | CFS!AF21 |
| Ratios!AF27 | Ratios\|27\|Ratios!r3 | Y27 | aggregation | SUM(AF24:AF26) | Ratios!AF24:AF26 |
| Ratios!AF8 | Ratios\|8\|Ratios!r3 | Y27 | same_period | -Construction!AE12 | Construction!AE12 |
| Ratios!AF9 | Ratios\|9\|Ratios!r3 | Y27 | same_period | -Construction!AE13 | Construction!AE13 |
| Ratios!AG10 | Ratios\|10\|Ratios!r3 | Y28 | same_period | -Construction!AF14 | Construction!AF14 |
| Ratios!AG11 | Ratios\|11\|Ratios!r3 | Y28 | same_period | -Construction!AF15 | Construction!AF15 |
| Ratios!AG12 | Ratios\|12\|Ratios!r3 | Y28 | aggregation | SUM(AG8:AG11) | Ratios!AG8:AG11 |
| Ratios!AG14 | Ratios\|14\|Ratios!r3 | Y28 | same_period | Operation!AF14 | Operation!AF14 |
| Ratios!AG15 | Ratios\|15\|Ratios!r3 | Y28 | same_period | -Operation!AF21 | Operation!AF21 |
| Ratios!AG16 | Ratios\|16\|Ratios!r3 | Y28 | same_period | 'P&L'!AG23 | P&L!AG23 |
| Ratios!AG17 | Ratios\|17\|Ratios!r3 | Y28 | aggregation | SUM(AG12:AG16) | Ratios!AG12:AG16 |
| Ratios!AG24 | Ratios\|24\|Ratios!r3 | Y28 | same_period | -Construction!AF26 | Construction!AF26 |
| Ratios!AG25 | Ratios\|25\|Ratios!r3 | Y28 | same_period | -CFS!AG21 | CFS!AG21 |
| Ratios!AG27 | Ratios\|27\|Ratios!r3 | Y28 | aggregation | SUM(AG24:AG26) | Ratios!AG24:AG26 |
| Ratios!AG8 | Ratios\|8\|Ratios!r3 | Y28 | same_period | -Construction!AF12 | Construction!AF12 |
| Ratios!AG9 | Ratios\|9\|Ratios!r3 | Y28 | same_period | -Construction!AF13 | Construction!AF13 |
| Ratios!AH10 | Ratios\|10\|Ratios!r3 | Y29 | same_period | -Construction!AG14 | Construction!AG14 |
| Ratios!AH11 | Ratios\|11\|Ratios!r3 | Y29 | same_period | -Construction!AG15 | Construction!AG15 |
| Ratios!AH12 | Ratios\|12\|Ratios!r3 | Y29 | aggregation | SUM(AH8:AH11) | Ratios!AH8:AH11 |
| Ratios!AH14 | Ratios\|14\|Ratios!r3 | Y29 | same_period | Operation!AG14 | Operation!AG14 |
| Ratios!AH15 | Ratios\|15\|Ratios!r3 | Y29 | same_period | -Operation!AG21 | Operation!AG21 |
| Ratios!AH16 | Ratios\|16\|Ratios!r3 | Y29 | same_period | 'P&L'!AH23 | P&L!AH23 |
| Ratios!AH17 | Ratios\|17\|Ratios!r3 | Y29 | aggregation | SUM(AH12:AH16) | Ratios!AH12:AH16 |
| Ratios!AH24 | Ratios\|24\|Ratios!r3 | Y29 | same_period | -Construction!AG26 | Construction!AG26 |
| Ratios!AH25 | Ratios\|25\|Ratios!r3 | Y29 | same_period | -CFS!AH21 | CFS!AH21 |
| Ratios!AH27 | Ratios\|27\|Ratios!r3 | Y29 | aggregation | SUM(AH24:AH26) | Ratios!AH24:AH26 |
| Ratios!AH8 | Ratios\|8\|Ratios!r3 | Y29 | same_period | -Construction!AG12 | Construction!AG12 |
| Ratios!AH9 | Ratios\|9\|Ratios!r3 | Y29 | same_period | -Construction!AG13 | Construction!AG13 |
| Ratios!AI10 | Ratios\|10\|Ratios!r3 | Y30 | same_period | -Construction!AH14 | Construction!AH14 |
| Ratios!AI11 | Ratios\|11\|Ratios!r3 | Y30 | same_period | -Construction!AH15 | Construction!AH15 |
| Ratios!AI12 | Ratios\|12\|Ratios!r3 | Y30 | aggregation | SUM(AI8:AI11) | Ratios!AI8:AI11 |
| Ratios!AI14 | Ratios\|14\|Ratios!r3 | Y30 | same_period | Operation!AH14 | Operation!AH14 |
| Ratios!AI15 | Ratios\|15\|Ratios!r3 | Y30 | same_period | -Operation!AH21 | Operation!AH21 |
| Ratios!AI16 | Ratios\|16\|Ratios!r3 | Y30 | same_period | 'P&L'!AI23 | P&L!AI23 |
| Ratios!AI17 | Ratios\|17\|Ratios!r3 | Y30 | aggregation | SUM(AI12:AI16) | Ratios!AI12:AI16 |
| Ratios!AI24 | Ratios\|24\|Ratios!r3 | Y30 | same_period | -Construction!AH26 | Construction!AH26 |
| Ratios!AI25 | Ratios\|25\|Ratios!r3 | Y30 | same_period | -CFS!AI21 | CFS!AI21 |
| Ratios!AI27 | Ratios\|27\|Ratios!r3 | Y30 | aggregation | SUM(AI24:AI26) | Ratios!AI24:AI26 |
| Ratios!AI8 | Ratios\|8\|Ratios!r3 | Y30 | same_period | -Construction!AH12 | Construction!AH12 |
| Ratios!AI9 | Ratios\|9\|Ratios!r3 | Y30 | same_period | -Construction!AH13 | Construction!AH13 |
| Ratios!AJ10 | Ratios\|10\|Ratios!r3 | Y31 | same_period | -Construction!AI14 | Construction!AI14 |
| Ratios!AJ11 | Ratios\|11\|Ratios!r3 | Y31 | same_period | -Construction!AI15 | Construction!AI15 |
| Ratios!AJ12 | Ratios\|12\|Ratios!r3 | Y31 | aggregation | SUM(AJ8:AJ11) | Ratios!AJ8:AJ11 |
| Ratios!AJ14 | Ratios\|14\|Ratios!r3 | Y31 | same_period | Operation!AI14 | Operation!AI14 |
| Ratios!AJ15 | Ratios\|15\|Ratios!r3 | Y31 | same_period | -Operation!AI21 | Operation!AI21 |
| Ratios!AJ16 | Ratios\|16\|Ratios!r3 | Y31 | same_period | 'P&L'!AJ23 | P&L!AJ23 |
| Ratios!AJ17 | Ratios\|17\|Ratios!r3 | Y31 | aggregation | SUM(AJ12:AJ16) | Ratios!AJ12:AJ16 |
| Ratios!AJ24 | Ratios\|24\|Ratios!r3 | Y31 | same_period | -Construction!AI26 | Construction!AI26 |
| Ratios!AJ25 | Ratios\|25\|Ratios!r3 | Y31 | same_period | -CFS!AJ21 | CFS!AJ21 |
| Ratios!AJ27 | Ratios\|27\|Ratios!r3 | Y31 | aggregation | SUM(AJ24:AJ26) | Ratios!AJ24:AJ26 |
| Ratios!AJ8 | Ratios\|8\|Ratios!r3 | Y31 | same_period | -Construction!AI12 | Construction!AI12 |
| Ratios!AJ9 | Ratios\|9\|Ratios!r3 | Y31 | same_period | -Construction!AI13 | Construction!AI13 |
| Ratios!AK10 | Ratios\|10\|Ratios!r3 | Y32 | same_period | -Construction!AJ14 | Construction!AJ14 |
| Ratios!AK11 | Ratios\|11\|Ratios!r3 | Y32 | same_period | -Construction!AJ15 | Construction!AJ15 |
| Ratios!AK12 | Ratios\|12\|Ratios!r3 | Y32 | aggregation | SUM(AK8:AK11) | Ratios!AK8:AK11 |
| Ratios!AK14 | Ratios\|14\|Ratios!r3 | Y32 | same_period | Operation!AJ14 | Operation!AJ14 |
| Ratios!AK15 | Ratios\|15\|Ratios!r3 | Y32 | same_period | -Operation!AJ21 | Operation!AJ21 |
| Ratios!AK16 | Ratios\|16\|Ratios!r3 | Y32 | same_period | 'P&L'!AK23 | P&L!AK23 |
| Ratios!AK17 | Ratios\|17\|Ratios!r3 | Y32 | aggregation | SUM(AK12:AK16) | Ratios!AK12:AK16 |
| Ratios!AK24 | Ratios\|24\|Ratios!r3 | Y32 | same_period | -Construction!AJ26 | Construction!AJ26 |
| Ratios!AK25 | Ratios\|25\|Ratios!r3 | Y32 | same_period | -CFS!AK21 | CFS!AK21 |
| Ratios!AK27 | Ratios\|27\|Ratios!r3 | Y32 | aggregation | SUM(AK24:AK26) | Ratios!AK24:AK26 |
| Ratios!AK8 | Ratios\|8\|Ratios!r3 | Y32 | same_period | -Construction!AJ12 | Construction!AJ12 |
| Ratios!AK9 | Ratios\|9\|Ratios!r3 | Y32 | same_period | -Construction!AJ13 | Construction!AJ13 |
| Ratios!AL10 | Ratios\|10\|Ratios!r3 | Y33 | same_period | -Construction!AK14 | Construction!AK14 |
| Ratios!AL11 | Ratios\|11\|Ratios!r3 | Y33 | same_period | -Construction!AK15 | Construction!AK15 |
| Ratios!AL12 | Ratios\|12\|Ratios!r3 | Y33 | aggregation | SUM(AL8:AL11) | Ratios!AL8:AL11 |
| Ratios!AL14 | Ratios\|14\|Ratios!r3 | Y33 | same_period | Operation!AK14 | Operation!AK14 |
| Ratios!AL15 | Ratios\|15\|Ratios!r3 | Y33 | same_period | -Operation!AK21 | Operation!AK21 |
| Ratios!AL16 | Ratios\|16\|Ratios!r3 | Y33 | same_period | 'P&L'!AL23 | P&L!AL23 |
| Ratios!AL17 | Ratios\|17\|Ratios!r3 | Y33 | aggregation | SUM(AL12:AL16) | Ratios!AL12:AL16 |
| Ratios!AL24 | Ratios\|24\|Ratios!r3 | Y33 | same_period | -Construction!AK26 | Construction!AK26 |
| Ratios!AL25 | Ratios\|25\|Ratios!r3 | Y33 | same_period | -CFS!AL21 | CFS!AL21 |
| Ratios!AL27 | Ratios\|27\|Ratios!r3 | Y33 | aggregation | SUM(AL24:AL26) | Ratios!AL24:AL26 |
| Ratios!AL8 | Ratios\|8\|Ratios!r3 | Y33 | same_period | -Construction!AK12 | Construction!AK12 |
| Ratios!AL9 | Ratios\|9\|Ratios!r3 | Y33 | same_period | -Construction!AK13 | Construction!AK13 |
| Ratios!AM10 | Ratios\|10\|Ratios!r3 | Y34 | same_period | -Construction!AL14 | Construction!AL14 |
| Ratios!AM11 | Ratios\|11\|Ratios!r3 | Y34 | same_period | -Construction!AL15 | Construction!AL15 |
| Ratios!AM12 | Ratios\|12\|Ratios!r3 | Y34 | aggregation | SUM(AM8:AM11) | Ratios!AM8:AM11 |
| Ratios!AM14 | Ratios\|14\|Ratios!r3 | Y34 | same_period | Operation!AL14 | Operation!AL14 |
| Ratios!AM15 | Ratios\|15\|Ratios!r3 | Y34 | same_period | -Operation!AL21 | Operation!AL21 |
| Ratios!AM16 | Ratios\|16\|Ratios!r3 | Y34 | same_period | 'P&L'!AM23 | P&L!AM23 |
| Ratios!AM17 | Ratios\|17\|Ratios!r3 | Y34 | aggregation | SUM(AM12:AM16) | Ratios!AM12:AM16 |
| Ratios!AM24 | Ratios\|24\|Ratios!r3 | Y34 | same_period | -Construction!AL26 | Construction!AL26 |
| Ratios!AM25 | Ratios\|25\|Ratios!r3 | Y34 | same_period | -CFS!AM21 | CFS!AM21 |
| Ratios!AM27 | Ratios\|27\|Ratios!r3 | Y34 | aggregation | SUM(AM24:AM26) | Ratios!AM24:AM26 |
| Ratios!AM8 | Ratios\|8\|Ratios!r3 | Y34 | same_period | -Construction!AL12 | Construction!AL12 |
| Ratios!AM9 | Ratios\|9\|Ratios!r3 | Y34 | same_period | -Construction!AL13 | Construction!AL13 |
| Ratios!AN10 | Ratios\|10\|Ratios!r3 | Y35 | same_period | -Construction!AM14 | Construction!AM14 |
| Ratios!AN11 | Ratios\|11\|Ratios!r3 | Y35 | same_period | -Construction!AM15 | Construction!AM15 |
| Ratios!AN12 | Ratios\|12\|Ratios!r3 | Y35 | aggregation | SUM(AN8:AN11) | Ratios!AN8:AN11 |
| Ratios!AN14 | Ratios\|14\|Ratios!r3 | Y35 | same_period | Operation!AM14 | Operation!AM14 |
| Ratios!AN15 | Ratios\|15\|Ratios!r3 | Y35 | same_period | -Operation!AM21 | Operation!AM21 |
| Ratios!AN16 | Ratios\|16\|Ratios!r3 | Y35 | same_period | 'P&L'!AN23 | P&L!AN23 |
| Ratios!AN17 | Ratios\|17\|Ratios!r3 | Y35 | aggregation | SUM(AN12:AN16) | Ratios!AN12:AN16 |
| Ratios!AN24 | Ratios\|24\|Ratios!r3 | Y35 | same_period | -Construction!AM26 | Construction!AM26 |
| Ratios!AN25 | Ratios\|25\|Ratios!r3 | Y35 | same_period | -CFS!AN21 | CFS!AN21 |
| Ratios!AN27 | Ratios\|27\|Ratios!r3 | Y35 | aggregation | SUM(AN24:AN26) | Ratios!AN24:AN26 |
| Ratios!AN8 | Ratios\|8\|Ratios!r3 | Y35 | same_period | -Construction!AM12 | Construction!AM12 |
| Ratios!AN9 | Ratios\|9\|Ratios!r3 | Y35 | same_period | -Construction!AM13 | Construction!AM13 |
| Ratios!AO10 | Ratios\|10\|Ratios!r3 | Y36 | same_period | -Construction!AN14 | Construction!AN14 |
| Ratios!AO11 | Ratios\|11\|Ratios!r3 | Y36 | same_period | -Construction!AN15 | Construction!AN15 |
| Ratios!AO12 | Ratios\|12\|Ratios!r3 | Y36 | aggregation | SUM(AO8:AO11) | Ratios!AO8:AO11 |
| Ratios!AO14 | Ratios\|14\|Ratios!r3 | Y36 | same_period | Operation!AN14 | Operation!AN14 |
| Ratios!AO15 | Ratios\|15\|Ratios!r3 | Y36 | same_period | -Operation!AN21 | Operation!AN21 |
| Ratios!AO16 | Ratios\|16\|Ratios!r3 | Y36 | same_period | 'P&L'!AO23 | P&L!AO23 |
| Ratios!AO17 | Ratios\|17\|Ratios!r3 | Y36 | aggregation | SUM(AO12:AO16) | Ratios!AO12:AO16 |
| Ratios!AO24 | Ratios\|24\|Ratios!r3 | Y36 | same_period | -Construction!AN26 | Construction!AN26 |
| Ratios!AO25 | Ratios\|25\|Ratios!r3 | Y36 | same_period | -CFS!AO21 | CFS!AO21 |
| Ratios!AO27 | Ratios\|27\|Ratios!r3 | Y36 | aggregation | SUM(AO24:AO26) | Ratios!AO24:AO26 |
| Ratios!AO8 | Ratios\|8\|Ratios!r3 | Y36 | same_period | -Construction!AN12 | Construction!AN12 |
| Ratios!AO9 | Ratios\|9\|Ratios!r3 | Y36 | same_period | -Construction!AN13 | Construction!AN13 |
| Ratios!AP10 | Ratios\|10\|Ratios!r3 | Y37 | same_period | -Construction!AO14 | Construction!AO14 |
| Ratios!AP11 | Ratios\|11\|Ratios!r3 | Y37 | same_period | -Construction!AO15 | Construction!AO15 |
| Ratios!AP12 | Ratios\|12\|Ratios!r3 | Y37 | aggregation | SUM(AP8:AP11) | Ratios!AP8:AP11 |
| Ratios!AP14 | Ratios\|14\|Ratios!r3 | Y37 | same_period | Operation!AO14 | Operation!AO14 |
| Ratios!AP15 | Ratios\|15\|Ratios!r3 | Y37 | same_period | -Operation!AO21 | Operation!AO21 |
| Ratios!AP16 | Ratios\|16\|Ratios!r3 | Y37 | same_period | 'P&L'!AP23 | P&L!AP23 |
| Ratios!AP17 | Ratios\|17\|Ratios!r3 | Y37 | aggregation | SUM(AP12:AP16) | Ratios!AP12:AP16 |
| Ratios!AP24 | Ratios\|24\|Ratios!r3 | Y37 | same_period | -Construction!AO26 | Construction!AO26 |
| Ratios!AP25 | Ratios\|25\|Ratios!r3 | Y37 | same_period | -CFS!AP21 | CFS!AP21 |
| Ratios!AP27 | Ratios\|27\|Ratios!r3 | Y37 | aggregation | SUM(AP24:AP26) | Ratios!AP24:AP26 |
| Ratios!AP8 | Ratios\|8\|Ratios!r3 | Y37 | same_period | -Construction!AO12 | Construction!AO12 |
| Ratios!AP9 | Ratios\|9\|Ratios!r3 | Y37 | same_period | -Construction!AO13 | Construction!AO13 |
| Ratios!AQ10 | Ratios\|10\|Ratios!r3 | Y38 | same_period | -Construction!AP14 | Construction!AP14 |
| Ratios!AQ11 | Ratios\|11\|Ratios!r3 | Y38 | same_period | -Construction!AP15 | Construction!AP15 |
| Ratios!AQ12 | Ratios\|12\|Ratios!r3 | Y38 | aggregation | SUM(AQ8:AQ11) | Ratios!AQ8:AQ11 |
| Ratios!AQ14 | Ratios\|14\|Ratios!r3 | Y38 | same_period | Operation!AP14 | Operation!AP14 |
| Ratios!AQ15 | Ratios\|15\|Ratios!r3 | Y38 | same_period | -Operation!AP21 | Operation!AP21 |
| Ratios!AQ16 | Ratios\|16\|Ratios!r3 | Y38 | same_period | 'P&L'!AQ23 | P&L!AQ23 |
| Ratios!AQ17 | Ratios\|17\|Ratios!r3 | Y38 | aggregation | SUM(AQ12:AQ16) | Ratios!AQ12:AQ16 |
| Ratios!AQ24 | Ratios\|24\|Ratios!r3 | Y38 | same_period | -Construction!AP26 | Construction!AP26 |
| Ratios!AQ25 | Ratios\|25\|Ratios!r3 | Y38 | same_period | -CFS!AQ21 | CFS!AQ21 |
| Ratios!AQ27 | Ratios\|27\|Ratios!r3 | Y38 | aggregation | SUM(AQ24:AQ26) | Ratios!AQ24:AQ26 |
| Ratios!AQ8 | Ratios\|8\|Ratios!r3 | Y38 | same_period | -Construction!AP12 | Construction!AP12 |
| Ratios!AQ9 | Ratios\|9\|Ratios!r3 | Y38 | same_period | -Construction!AP13 | Construction!AP13 |
| Ratios!AR10 | Ratios\|10\|Ratios!r3 | Y39 | same_period | -Construction!AQ14 | Construction!AQ14 |
| Ratios!AR11 | Ratios\|11\|Ratios!r3 | Y39 | same_period | -Construction!AQ15 | Construction!AQ15 |
| Ratios!AR12 | Ratios\|12\|Ratios!r3 | Y39 | aggregation | SUM(AR8:AR11) | Ratios!AR8:AR11 |
| Ratios!AR14 | Ratios\|14\|Ratios!r3 | Y39 | same_period | Operation!AQ14 | Operation!AQ14 |
| Ratios!AR15 | Ratios\|15\|Ratios!r3 | Y39 | same_period | -Operation!AQ21 | Operation!AQ21 |
| Ratios!AR16 | Ratios\|16\|Ratios!r3 | Y39 | same_period | 'P&L'!AR23 | P&L!AR23 |
| Ratios!AR17 | Ratios\|17\|Ratios!r3 | Y39 | aggregation | SUM(AR12:AR16) | Ratios!AR12:AR16 |
| Ratios!AR24 | Ratios\|24\|Ratios!r3 | Y39 | same_period | -Construction!AQ26 | Construction!AQ26 |
| Ratios!AR25 | Ratios\|25\|Ratios!r3 | Y39 | same_period | -CFS!AR21 | CFS!AR21 |
| Ratios!AR27 | Ratios\|27\|Ratios!r3 | Y39 | aggregation | SUM(AR24:AR26) | Ratios!AR24:AR26 |
| Ratios!AR8 | Ratios\|8\|Ratios!r3 | Y39 | same_period | -Construction!AQ12 | Construction!AQ12 |
| Ratios!AR9 | Ratios\|9\|Ratios!r3 | Y39 | same_period | -Construction!AQ13 | Construction!AQ13 |
| Ratios!AS10 | Ratios\|10\|Ratios!r3 | Y40 | same_period | -Construction!AR14 | Construction!AR14 |
| Ratios!AS11 | Ratios\|11\|Ratios!r3 | Y40 | same_period | -Construction!AR15 | Construction!AR15 |
| Ratios!AS12 | Ratios\|12\|Ratios!r3 | Y40 | aggregation | SUM(AS8:AS11) | Ratios!AS8:AS11 |
| Ratios!AS14 | Ratios\|14\|Ratios!r3 | Y40 | same_period | Operation!AR14 | Operation!AR14 |
| Ratios!AS15 | Ratios\|15\|Ratios!r3 | Y40 | same_period | -Operation!AR21 | Operation!AR21 |
| Ratios!AS16 | Ratios\|16\|Ratios!r3 | Y40 | same_period | 'P&L'!AS23 | P&L!AS23 |
| Ratios!AS17 | Ratios\|17\|Ratios!r3 | Y40 | aggregation | SUM(AS12:AS16) | Ratios!AS12:AS16 |
| Ratios!AS24 | Ratios\|24\|Ratios!r3 | Y40 | same_period | -Construction!AR26 | Construction!AR26 |
| Ratios!AS25 | Ratios\|25\|Ratios!r3 | Y40 | same_period | -CFS!AS21 | CFS!AS21 |
| Ratios!AS26 | Ratios\|26\|Ratios!r3 | Y40 | same_period | 'Balance Sheet'!AS9 | Balance Sheet!AS9 |
| Ratios!AS27 | Ratios\|27\|Ratios!r3 | Y40 | aggregation | SUM(AS24:AS26) | Ratios!AS24:AS26 |
| Ratios!AS8 | Ratios\|8\|Ratios!r3 | Y40 | same_period | -Construction!AR12 | Construction!AR12 |
| Ratios!AS9 | Ratios\|9\|Ratios!r3 | Y40 | same_period | -Construction!AR13 | Construction!AR13 |
| Ratios!E12 | Ratios\|12\|Ratios!r3 |  | aggregation | SUM(F12:AS12) | Ratios!F12:AS12 |
| Ratios!E19 | Ratios\|19\|Ratios!r3 |  | same_period | IRR(F17:AS17) | Ratios!F17:AS17 |
| Ratios!E24 | Ratios\|24\|Ratios!r3 |  | aggregation | SUM(F24:AS24) | Ratios!F24:AS24 |
| Ratios!E29 | Ratios\|29\|Ratios!r3 |  | same_period | IRR(F27:AS27) | Ratios!F27:AS27 |
| Ratios!F10 | Ratios\|10\|Ratios!r3 | Y1 | same_period | -Construction!E14 | Construction!E14 |
| Ratios!F11 | Ratios\|11\|Ratios!r3 | Y1 | same_period | -Construction!E15 | Construction!E15 |
| Ratios!F12 | Ratios\|12\|Ratios!r3 | Y1 | aggregation | SUM(F8:F11) | Ratios!F8:F11 |
| Ratios!F14 | Ratios\|14\|Ratios!r3 | Y1 | same_period | Operation!E14 | Operation!E14 |
| Ratios!F15 | Ratios\|15\|Ratios!r3 | Y1 | same_period | -Operation!E21 | Operation!E21 |
| Ratios!F16 | Ratios\|16\|Ratios!r3 | Y1 | same_period | 'P&L'!F23 | P&L!F23 |
| Ratios!F17 | Ratios\|17\|Ratios!r3 | Y1 | aggregation | SUM(F12:F16) | Ratios!F12:F16 |
| Ratios!F24 | Ratios\|24\|Ratios!r3 | Y1 | same_period | -Construction!E26 | Construction!E26 |
| Ratios!F25 | Ratios\|25\|Ratios!r3 | Y1 | same_period | -CFS!F21 | CFS!F21 |
| Ratios!F27 | Ratios\|27\|Ratios!r3 | Y1 | aggregation | SUM(F24:F26) | Ratios!F24:F26 |
| Ratios!F8 | Ratios\|8\|Ratios!r3 | Y1 | same_period | -Construction!E12 | Construction!E12 |
| Ratios!F9 | Ratios\|9\|Ratios!r3 | Y1 | same_period | -Construction!E13 | Construction!E13 |
| Ratios!G10 | Ratios\|10\|Ratios!r3 | Y2 | same_period | -Construction!F14 | Construction!F14 |
| Ratios!G11 | Ratios\|11\|Ratios!r3 | Y2 | same_period | -Construction!F15 | Construction!F15 |
| Ratios!G12 | Ratios\|12\|Ratios!r3 | Y2 | aggregation | SUM(G8:G11) | Ratios!G8:G11 |
| Ratios!G14 | Ratios\|14\|Ratios!r3 | Y2 | same_period | Operation!F14 | Operation!F14 |
| Ratios!G15 | Ratios\|15\|Ratios!r3 | Y2 | same_period | -Operation!F21 | Operation!F21 |
| Ratios!G16 | Ratios\|16\|Ratios!r3 | Y2 | same_period | 'P&L'!G23 | P&L!G23 |
| Ratios!G17 | Ratios\|17\|Ratios!r3 | Y2 | aggregation | SUM(G12:G16) | Ratios!G12:G16 |
| Ratios!G24 | Ratios\|24\|Ratios!r3 | Y2 | same_period | -Construction!F26 | Construction!F26 |
| Ratios!G25 | Ratios\|25\|Ratios!r3 | Y2 | same_period | -CFS!G21 | CFS!G21 |
| Ratios!G27 | Ratios\|27\|Ratios!r3 | Y2 | aggregation | SUM(G24:G26) | Ratios!G24:G26 |
| Ratios!G8 | Ratios\|8\|Ratios!r3 | Y2 | same_period | -Construction!F12 | Construction!F12 |
| Ratios!G9 | Ratios\|9\|Ratios!r3 | Y2 | same_period | -Construction!F13 | Construction!F13 |
| Ratios!H10 | Ratios\|10\|Ratios!r3 | Y3 | same_period | -Construction!G14 | Construction!G14 |
| Ratios!H11 | Ratios\|11\|Ratios!r3 | Y3 | same_period | -Construction!G15 | Construction!G15 |
| Ratios!H12 | Ratios\|12\|Ratios!r3 | Y3 | aggregation | SUM(H8:H11) | Ratios!H8:H11 |
| Ratios!H14 | Ratios\|14\|Ratios!r3 | Y3 | same_period | Operation!G14 | Operation!G14 |
| Ratios!H15 | Ratios\|15\|Ratios!r3 | Y3 | same_period | -Operation!G21 | Operation!G21 |
| Ratios!H16 | Ratios\|16\|Ratios!r3 | Y3 | same_period | 'P&L'!H23 | P&L!H23 |
| Ratios!H17 | Ratios\|17\|Ratios!r3 | Y3 | aggregation | SUM(H12:H16) | Ratios!H12:H16 |
| Ratios!H24 | Ratios\|24\|Ratios!r3 | Y3 | same_period | -Construction!G26 | Construction!G26 |
| Ratios!H25 | Ratios\|25\|Ratios!r3 | Y3 | same_period | -CFS!H21 | CFS!H21 |
| Ratios!H27 | Ratios\|27\|Ratios!r3 | Y3 | aggregation | SUM(H24:H26) | Ratios!H24:H26 |
| Ratios!H8 | Ratios\|8\|Ratios!r3 | Y3 | same_period | -Construction!G12 | Construction!G12 |
| Ratios!H9 | Ratios\|9\|Ratios!r3 | Y3 | same_period | -Construction!G13 | Construction!G13 |
| Ratios!I10 | Ratios\|10\|Ratios!r3 | Y4 | same_period | -Construction!H14 | Construction!H14 |
| Ratios!I11 | Ratios\|11\|Ratios!r3 | Y4 | same_period | -Construction!H15 | Construction!H15 |
| Ratios!I12 | Ratios\|12\|Ratios!r3 | Y4 | aggregation | SUM(I8:I11) | Ratios!I8:I11 |
| Ratios!I14 | Ratios\|14\|Ratios!r3 | Y4 | same_period | Operation!H14 | Operation!H14 |
| Ratios!I15 | Ratios\|15\|Ratios!r3 | Y4 | same_period | -Operation!H21 | Operation!H21 |
| Ratios!I16 | Ratios\|16\|Ratios!r3 | Y4 | same_period | 'P&L'!I23 | P&L!I23 |
| Ratios!I17 | Ratios\|17\|Ratios!r3 | Y4 | aggregation | SUM(I12:I16) | Ratios!I12:I16 |
| Ratios!I24 | Ratios\|24\|Ratios!r3 | Y4 | same_period | -Construction!H26 | Construction!H26 |
| Ratios!I25 | Ratios\|25\|Ratios!r3 | Y4 | same_period | -CFS!I21 | CFS!I21 |
| Ratios!I27 | Ratios\|27\|Ratios!r3 | Y4 | aggregation | SUM(I24:I26) | Ratios!I24:I26 |
| Ratios!I8 | Ratios\|8\|Ratios!r3 | Y4 | same_period | -Construction!H12 | Construction!H12 |
| Ratios!I9 | Ratios\|9\|Ratios!r3 | Y4 | same_period | -Construction!H13 | Construction!H13 |
| Ratios!J10 | Ratios\|10\|Ratios!r3 | Y5 | same_period | -Construction!I14 | Construction!I14 |
| Ratios!J11 | Ratios\|11\|Ratios!r3 | Y5 | same_period | -Construction!I15 | Construction!I15 |
| Ratios!J12 | Ratios\|12\|Ratios!r3 | Y5 | aggregation | SUM(J8:J11) | Ratios!J8:J11 |
| Ratios!J14 | Ratios\|14\|Ratios!r3 | Y5 | same_period | Operation!I14 | Operation!I14 |
| Ratios!J15 | Ratios\|15\|Ratios!r3 | Y5 | same_period | -Operation!I21 | Operation!I21 |
| Ratios!J16 | Ratios\|16\|Ratios!r3 | Y5 | same_period | 'P&L'!J23 | P&L!J23 |
| Ratios!J17 | Ratios\|17\|Ratios!r3 | Y5 | aggregation | SUM(J12:J16) | Ratios!J12:J16 |
| Ratios!J24 | Ratios\|24\|Ratios!r3 | Y5 | same_period | -Construction!I26 | Construction!I26 |
| Ratios!J25 | Ratios\|25\|Ratios!r3 | Y5 | same_period | -CFS!J21 | CFS!J21 |
| Ratios!J27 | Ratios\|27\|Ratios!r3 | Y5 | aggregation | SUM(J24:J26) | Ratios!J24:J26 |
| Ratios!J8 | Ratios\|8\|Ratios!r3 | Y5 | same_period | -Construction!I12 | Construction!I12 |
| Ratios!J9 | Ratios\|9\|Ratios!r3 | Y5 | same_period | -Construction!I13 | Construction!I13 |
| Ratios!K10 | Ratios\|10\|Ratios!r3 | Y6 | same_period | -Construction!J14 | Construction!J14 |
| Ratios!K11 | Ratios\|11\|Ratios!r3 | Y6 | same_period | -Construction!J15 | Construction!J15 |
| Ratios!K12 | Ratios\|12\|Ratios!r3 | Y6 | aggregation | SUM(K8:K11) | Ratios!K8:K11 |
| Ratios!K14 | Ratios\|14\|Ratios!r3 | Y6 | same_period | Operation!J14 | Operation!J14 |
| Ratios!K15 | Ratios\|15\|Ratios!r3 | Y6 | same_period | -Operation!J21 | Operation!J21 |
| Ratios!K16 | Ratios\|16\|Ratios!r3 | Y6 | same_period | 'P&L'!K23 | P&L!K23 |
| Ratios!K17 | Ratios\|17\|Ratios!r3 | Y6 | aggregation | SUM(K12:K16) | Ratios!K12:K16 |
| Ratios!K24 | Ratios\|24\|Ratios!r3 | Y6 | same_period | -Construction!J26 | Construction!J26 |
| Ratios!K25 | Ratios\|25\|Ratios!r3 | Y6 | same_period | -CFS!K21 | CFS!K21 |
| Ratios!K27 | Ratios\|27\|Ratios!r3 | Y6 | aggregation | SUM(K24:K26) | Ratios!K24:K26 |
| Ratios!K8 | Ratios\|8\|Ratios!r3 | Y6 | same_period | -Construction!J12 | Construction!J12 |
| Ratios!K9 | Ratios\|9\|Ratios!r3 | Y6 | same_period | -Construction!J13 | Construction!J13 |
| Ratios!L10 | Ratios\|10\|Ratios!r3 | Y7 | same_period | -Construction!K14 | Construction!K14 |
| Ratios!L11 | Ratios\|11\|Ratios!r3 | Y7 | same_period | -Construction!K15 | Construction!K15 |
| Ratios!L12 | Ratios\|12\|Ratios!r3 | Y7 | aggregation | SUM(L8:L11) | Ratios!L8:L11 |
| Ratios!L14 | Ratios\|14\|Ratios!r3 | Y7 | same_period | Operation!K14 | Operation!K14 |
| Ratios!L15 | Ratios\|15\|Ratios!r3 | Y7 | same_period | -Operation!K21 | Operation!K21 |
| Ratios!L16 | Ratios\|16\|Ratios!r3 | Y7 | same_period | 'P&L'!L23 | P&L!L23 |
| Ratios!L17 | Ratios\|17\|Ratios!r3 | Y7 | aggregation | SUM(L12:L16) | Ratios!L12:L16 |
| Ratios!L24 | Ratios\|24\|Ratios!r3 | Y7 | same_period | -Construction!K26 | Construction!K26 |
| Ratios!L25 | Ratios\|25\|Ratios!r3 | Y7 | same_period | -CFS!L21 | CFS!L21 |
| Ratios!L27 | Ratios\|27\|Ratios!r3 | Y7 | aggregation | SUM(L24:L26) | Ratios!L24:L26 |
| Ratios!L8 | Ratios\|8\|Ratios!r3 | Y7 | same_period | -Construction!K12 | Construction!K12 |
| Ratios!L9 | Ratios\|9\|Ratios!r3 | Y7 | same_period | -Construction!K13 | Construction!K13 |
| Ratios!M10 | Ratios\|10\|Ratios!r3 | Y8 | same_period | -Construction!L14 | Construction!L14 |
| Ratios!M11 | Ratios\|11\|Ratios!r3 | Y8 | same_period | -Construction!L15 | Construction!L15 |
| Ratios!M12 | Ratios\|12\|Ratios!r3 | Y8 | aggregation | SUM(M8:M11) | Ratios!M8:M11 |
| Ratios!M14 | Ratios\|14\|Ratios!r3 | Y8 | same_period | Operation!L14 | Operation!L14 |
| Ratios!M15 | Ratios\|15\|Ratios!r3 | Y8 | same_period | -Operation!L21 | Operation!L21 |
| Ratios!M16 | Ratios\|16\|Ratios!r3 | Y8 | same_period | 'P&L'!M23 | P&L!M23 |
| Ratios!M17 | Ratios\|17\|Ratios!r3 | Y8 | aggregation | SUM(M12:M16) | Ratios!M12:M16 |
| Ratios!M24 | Ratios\|24\|Ratios!r3 | Y8 | same_period | -Construction!L26 | Construction!L26 |
| Ratios!M25 | Ratios\|25\|Ratios!r3 | Y8 | same_period | -CFS!M21 | CFS!M21 |
| Ratios!M27 | Ratios\|27\|Ratios!r3 | Y8 | aggregation | SUM(M24:M26) | Ratios!M24:M26 |
| Ratios!M8 | Ratios\|8\|Ratios!r3 | Y8 | same_period | -Construction!L12 | Construction!L12 |
| Ratios!M9 | Ratios\|9\|Ratios!r3 | Y8 | same_period | -Construction!L13 | Construction!L13 |
| Ratios!N10 | Ratios\|10\|Ratios!r3 | Y9 | same_period | -Construction!M14 | Construction!M14 |
| Ratios!N11 | Ratios\|11\|Ratios!r3 | Y9 | same_period | -Construction!M15 | Construction!M15 |
| Ratios!N12 | Ratios\|12\|Ratios!r3 | Y9 | aggregation | SUM(N8:N11) | Ratios!N8:N11 |
| Ratios!N14 | Ratios\|14\|Ratios!r3 | Y9 | same_period | Operation!M14 | Operation!M14 |
| Ratios!N15 | Ratios\|15\|Ratios!r3 | Y9 | same_period | -Operation!M21 | Operation!M21 |
| Ratios!N16 | Ratios\|16\|Ratios!r3 | Y9 | same_period | 'P&L'!N23 | P&L!N23 |
| Ratios!N17 | Ratios\|17\|Ratios!r3 | Y9 | aggregation | SUM(N12:N16) | Ratios!N12:N16 |
| Ratios!N24 | Ratios\|24\|Ratios!r3 | Y9 | same_period | -Construction!M26 | Construction!M26 |
| Ratios!N25 | Ratios\|25\|Ratios!r3 | Y9 | same_period | -CFS!N21 | CFS!N21 |
| Ratios!N27 | Ratios\|27\|Ratios!r3 | Y9 | aggregation | SUM(N24:N26) | Ratios!N24:N26 |
| Ratios!N8 | Ratios\|8\|Ratios!r3 | Y9 | same_period | -Construction!M12 | Construction!M12 |
| Ratios!N9 | Ratios\|9\|Ratios!r3 | Y9 | same_period | -Construction!M13 | Construction!M13 |
| Ratios!O10 | Ratios\|10\|Ratios!r3 | Y10 | same_period | -Construction!N14 | Construction!N14 |
| Ratios!O11 | Ratios\|11\|Ratios!r3 | Y10 | same_period | -Construction!N15 | Construction!N15 |
| Ratios!O12 | Ratios\|12\|Ratios!r3 | Y10 | aggregation | SUM(O8:O11) | Ratios!O8:O11 |
| Ratios!O14 | Ratios\|14\|Ratios!r3 | Y10 | same_period | Operation!N14 | Operation!N14 |
| Ratios!O15 | Ratios\|15\|Ratios!r3 | Y10 | same_period | -Operation!N21 | Operation!N21 |
| Ratios!O16 | Ratios\|16\|Ratios!r3 | Y10 | same_period | 'P&L'!O23 | P&L!O23 |
| Ratios!O17 | Ratios\|17\|Ratios!r3 | Y10 | aggregation | SUM(O12:O16) | Ratios!O12:O16 |
| Ratios!O24 | Ratios\|24\|Ratios!r3 | Y10 | same_period | -Construction!N26 | Construction!N26 |
| Ratios!O25 | Ratios\|25\|Ratios!r3 | Y10 | same_period | -CFS!O21 | CFS!O21 |
| Ratios!O27 | Ratios\|27\|Ratios!r3 | Y10 | aggregation | SUM(O24:O26) | Ratios!O24:O26 |
| Ratios!O8 | Ratios\|8\|Ratios!r3 | Y10 | same_period | -Construction!N12 | Construction!N12 |
| Ratios!O9 | Ratios\|9\|Ratios!r3 | Y10 | same_period | -Construction!N13 | Construction!N13 |
| Ratios!P10 | Ratios\|10\|Ratios!r3 | Y11 | same_period | -Construction!O14 | Construction!O14 |
| Ratios!P11 | Ratios\|11\|Ratios!r3 | Y11 | same_period | -Construction!O15 | Construction!O15 |
| Ratios!P12 | Ratios\|12\|Ratios!r3 | Y11 | aggregation | SUM(P8:P11) | Ratios!P8:P11 |
| Ratios!P14 | Ratios\|14\|Ratios!r3 | Y11 | same_period | Operation!O14 | Operation!O14 |
| Ratios!P15 | Ratios\|15\|Ratios!r3 | Y11 | same_period | -Operation!O21 | Operation!O21 |
| Ratios!P16 | Ratios\|16\|Ratios!r3 | Y11 | same_period | 'P&L'!P23 | P&L!P23 |
| Ratios!P17 | Ratios\|17\|Ratios!r3 | Y11 | aggregation | SUM(P12:P16) | Ratios!P12:P16 |
| Ratios!P24 | Ratios\|24\|Ratios!r3 | Y11 | same_period | -Construction!O26 | Construction!O26 |
| Ratios!P25 | Ratios\|25\|Ratios!r3 | Y11 | same_period | -CFS!P21 | CFS!P21 |
| Ratios!P27 | Ratios\|27\|Ratios!r3 | Y11 | aggregation | SUM(P24:P26) | Ratios!P24:P26 |
| Ratios!P8 | Ratios\|8\|Ratios!r3 | Y11 | same_period | -Construction!O12 | Construction!O12 |
| Ratios!P9 | Ratios\|9\|Ratios!r3 | Y11 | same_period | -Construction!O13 | Construction!O13 |
| Ratios!Q10 | Ratios\|10\|Ratios!r3 | Y12 | same_period | -Construction!P14 | Construction!P14 |
| Ratios!Q11 | Ratios\|11\|Ratios!r3 | Y12 | same_period | -Construction!P15 | Construction!P15 |
| Ratios!Q12 | Ratios\|12\|Ratios!r3 | Y12 | aggregation | SUM(Q8:Q11) | Ratios!Q8:Q11 |
| Ratios!Q14 | Ratios\|14\|Ratios!r3 | Y12 | same_period | Operation!P14 | Operation!P14 |
| Ratios!Q15 | Ratios\|15\|Ratios!r3 | Y12 | same_period | -Operation!P21 | Operation!P21 |
| Ratios!Q16 | Ratios\|16\|Ratios!r3 | Y12 | same_period | 'P&L'!Q23 | P&L!Q23 |
| Ratios!Q17 | Ratios\|17\|Ratios!r3 | Y12 | aggregation | SUM(Q12:Q16) | Ratios!Q12:Q16 |
| Ratios!Q24 | Ratios\|24\|Ratios!r3 | Y12 | same_period | -Construction!P26 | Construction!P26 |
| Ratios!Q25 | Ratios\|25\|Ratios!r3 | Y12 | same_period | -CFS!Q21 | CFS!Q21 |
| Ratios!Q27 | Ratios\|27\|Ratios!r3 | Y12 | aggregation | SUM(Q24:Q26) | Ratios!Q24:Q26 |
| Ratios!Q8 | Ratios\|8\|Ratios!r3 | Y12 | same_period | -Construction!P12 | Construction!P12 |
| Ratios!Q9 | Ratios\|9\|Ratios!r3 | Y12 | same_period | -Construction!P13 | Construction!P13 |
| Ratios!R10 | Ratios\|10\|Ratios!r3 | Y13 | same_period | -Construction!Q14 | Construction!Q14 |
| Ratios!R11 | Ratios\|11\|Ratios!r3 | Y13 | same_period | -Construction!Q15 | Construction!Q15 |
| Ratios!R12 | Ratios\|12\|Ratios!r3 | Y13 | aggregation | SUM(R8:R11) | Ratios!R8:R11 |
| Ratios!R14 | Ratios\|14\|Ratios!r3 | Y13 | same_period | Operation!Q14 | Operation!Q14 |
| Ratios!R15 | Ratios\|15\|Ratios!r3 | Y13 | same_period | -Operation!Q21 | Operation!Q21 |
| Ratios!R16 | Ratios\|16\|Ratios!r3 | Y13 | same_period | 'P&L'!R23 | P&L!R23 |
| Ratios!R17 | Ratios\|17\|Ratios!r3 | Y13 | aggregation | SUM(R12:R16) | Ratios!R12:R16 |
| Ratios!R24 | Ratios\|24\|Ratios!r3 | Y13 | same_period | -Construction!Q26 | Construction!Q26 |
| Ratios!R25 | Ratios\|25\|Ratios!r3 | Y13 | same_period | -CFS!R21 | CFS!R21 |
| Ratios!R27 | Ratios\|27\|Ratios!r3 | Y13 | aggregation | SUM(R24:R26) | Ratios!R24:R26 |
| Ratios!R8 | Ratios\|8\|Ratios!r3 | Y13 | same_period | -Construction!Q12 | Construction!Q12 |
| Ratios!R9 | Ratios\|9\|Ratios!r3 | Y13 | same_period | -Construction!Q13 | Construction!Q13 |
| Ratios!S10 | Ratios\|10\|Ratios!r3 | Y14 | same_period | -Construction!R14 | Construction!R14 |
| Ratios!S11 | Ratios\|11\|Ratios!r3 | Y14 | same_period | -Construction!R15 | Construction!R15 |
| Ratios!S12 | Ratios\|12\|Ratios!r3 | Y14 | aggregation | SUM(S8:S11) | Ratios!S8:S11 |
| Ratios!S14 | Ratios\|14\|Ratios!r3 | Y14 | same_period | Operation!R14 | Operation!R14 |
| Ratios!S15 | Ratios\|15\|Ratios!r3 | Y14 | same_period | -Operation!R21 | Operation!R21 |
| Ratios!S16 | Ratios\|16\|Ratios!r3 | Y14 | same_period | 'P&L'!S23 | P&L!S23 |
| Ratios!S17 | Ratios\|17\|Ratios!r3 | Y14 | aggregation | SUM(S12:S16) | Ratios!S12:S16 |
| Ratios!S24 | Ratios\|24\|Ratios!r3 | Y14 | same_period | -Construction!R26 | Construction!R26 |
| Ratios!S25 | Ratios\|25\|Ratios!r3 | Y14 | same_period | -CFS!S21 | CFS!S21 |
| Ratios!S27 | Ratios\|27\|Ratios!r3 | Y14 | aggregation | SUM(S24:S26) | Ratios!S24:S26 |
| Ratios!S8 | Ratios\|8\|Ratios!r3 | Y14 | same_period | -Construction!R12 | Construction!R12 |
| Ratios!S9 | Ratios\|9\|Ratios!r3 | Y14 | same_period | -Construction!R13 | Construction!R13 |
| Ratios!T10 | Ratios\|10\|Ratios!r3 | Y15 | same_period | -Construction!S14 | Construction!S14 |
| Ratios!T11 | Ratios\|11\|Ratios!r3 | Y15 | same_period | -Construction!S15 | Construction!S15 |
| Ratios!T12 | Ratios\|12\|Ratios!r3 | Y15 | aggregation | SUM(T8:T11) | Ratios!T8:T11 |
| Ratios!T14 | Ratios\|14\|Ratios!r3 | Y15 | same_period | Operation!S14 | Operation!S14 |
| Ratios!T15 | Ratios\|15\|Ratios!r3 | Y15 | same_period | -Operation!S21 | Operation!S21 |
| Ratios!T16 | Ratios\|16\|Ratios!r3 | Y15 | same_period | 'P&L'!T23 | P&L!T23 |
| Ratios!T17 | Ratios\|17\|Ratios!r3 | Y15 | aggregation | SUM(T12:T16) | Ratios!T12:T16 |
| Ratios!T24 | Ratios\|24\|Ratios!r3 | Y15 | same_period | -Construction!S26 | Construction!S26 |
| Ratios!T25 | Ratios\|25\|Ratios!r3 | Y15 | same_period | -CFS!T21 | CFS!T21 |
| Ratios!T27 | Ratios\|27\|Ratios!r3 | Y15 | aggregation | SUM(T24:T26) | Ratios!T24:T26 |
| Ratios!T8 | Ratios\|8\|Ratios!r3 | Y15 | same_period | -Construction!S12 | Construction!S12 |
| Ratios!T9 | Ratios\|9\|Ratios!r3 | Y15 | same_period | -Construction!S13 | Construction!S13 |
| Ratios!U10 | Ratios\|10\|Ratios!r3 | Y16 | same_period | -Construction!T14 | Construction!T14 |
| Ratios!U11 | Ratios\|11\|Ratios!r3 | Y16 | same_period | -Construction!T15 | Construction!T15 |
| Ratios!U12 | Ratios\|12\|Ratios!r3 | Y16 | aggregation | SUM(U8:U11) | Ratios!U8:U11 |
| Ratios!U14 | Ratios\|14\|Ratios!r3 | Y16 | same_period | Operation!T14 | Operation!T14 |
| Ratios!U15 | Ratios\|15\|Ratios!r3 | Y16 | same_period | -Operation!T21 | Operation!T21 |
| Ratios!U16 | Ratios\|16\|Ratios!r3 | Y16 | same_period | 'P&L'!U23 | P&L!U23 |
| Ratios!U17 | Ratios\|17\|Ratios!r3 | Y16 | aggregation | SUM(U12:U16) | Ratios!U12:U16 |
| Ratios!U24 | Ratios\|24\|Ratios!r3 | Y16 | same_period | -Construction!T26 | Construction!T26 |
| Ratios!U25 | Ratios\|25\|Ratios!r3 | Y16 | same_period | -CFS!U21 | CFS!U21 |
| Ratios!U27 | Ratios\|27\|Ratios!r3 | Y16 | aggregation | SUM(U24:U26) | Ratios!U24:U26 |
| Ratios!U8 | Ratios\|8\|Ratios!r3 | Y16 | same_period | -Construction!T12 | Construction!T12 |
| Ratios!U9 | Ratios\|9\|Ratios!r3 | Y16 | same_period | -Construction!T13 | Construction!T13 |
| Ratios!V10 | Ratios\|10\|Ratios!r3 | Y17 | same_period | -Construction!U14 | Construction!U14 |
| Ratios!V11 | Ratios\|11\|Ratios!r3 | Y17 | same_period | -Construction!U15 | Construction!U15 |
| Ratios!V12 | Ratios\|12\|Ratios!r3 | Y17 | aggregation | SUM(V8:V11) | Ratios!V8:V11 |
| Ratios!V14 | Ratios\|14\|Ratios!r3 | Y17 | same_period | Operation!U14 | Operation!U14 |
| Ratios!V15 | Ratios\|15\|Ratios!r3 | Y17 | same_period | -Operation!U21 | Operation!U21 |
| Ratios!V16 | Ratios\|16\|Ratios!r3 | Y17 | same_period | 'P&L'!V23 | P&L!V23 |
| Ratios!V17 | Ratios\|17\|Ratios!r3 | Y17 | aggregation | SUM(V12:V16) | Ratios!V12:V16 |
| Ratios!V24 | Ratios\|24\|Ratios!r3 | Y17 | same_period | -Construction!U26 | Construction!U26 |
| Ratios!V25 | Ratios\|25\|Ratios!r3 | Y17 | same_period | -CFS!V21 | CFS!V21 |
| Ratios!V27 | Ratios\|27\|Ratios!r3 | Y17 | aggregation | SUM(V24:V26) | Ratios!V24:V26 |
| Ratios!V8 | Ratios\|8\|Ratios!r3 | Y17 | same_period | -Construction!U12 | Construction!U12 |
| Ratios!V9 | Ratios\|9\|Ratios!r3 | Y17 | same_period | -Construction!U13 | Construction!U13 |
| Ratios!W10 | Ratios\|10\|Ratios!r3 | Y18 | same_period | -Construction!V14 | Construction!V14 |
| Ratios!W11 | Ratios\|11\|Ratios!r3 | Y18 | same_period | -Construction!V15 | Construction!V15 |
| Ratios!W12 | Ratios\|12\|Ratios!r3 | Y18 | aggregation | SUM(W8:W11) | Ratios!W8:W11 |
| Ratios!W14 | Ratios\|14\|Ratios!r3 | Y18 | same_period | Operation!V14 | Operation!V14 |
| Ratios!W15 | Ratios\|15\|Ratios!r3 | Y18 | same_period | -Operation!V21 | Operation!V21 |
| Ratios!W16 | Ratios\|16\|Ratios!r3 | Y18 | same_period | 'P&L'!W23 | P&L!W23 |
| Ratios!W17 | Ratios\|17\|Ratios!r3 | Y18 | aggregation | SUM(W12:W16) | Ratios!W12:W16 |
| Ratios!W24 | Ratios\|24\|Ratios!r3 | Y18 | same_period | -Construction!V26 | Construction!V26 |
| Ratios!W25 | Ratios\|25\|Ratios!r3 | Y18 | same_period | -CFS!W21 | CFS!W21 |
| Ratios!W27 | Ratios\|27\|Ratios!r3 | Y18 | aggregation | SUM(W24:W26) | Ratios!W24:W26 |
| Ratios!W8 | Ratios\|8\|Ratios!r3 | Y18 | same_period | -Construction!V12 | Construction!V12 |
| Ratios!W9 | Ratios\|9\|Ratios!r3 | Y18 | same_period | -Construction!V13 | Construction!V13 |
| Ratios!X10 | Ratios\|10\|Ratios!r3 | Y19 | same_period | -Construction!W14 | Construction!W14 |
| Ratios!X11 | Ratios\|11\|Ratios!r3 | Y19 | same_period | -Construction!W15 | Construction!W15 |
| Ratios!X12 | Ratios\|12\|Ratios!r3 | Y19 | aggregation | SUM(X8:X11) | Ratios!X8:X11 |
| Ratios!X14 | Ratios\|14\|Ratios!r3 | Y19 | same_period | Operation!W14 | Operation!W14 |
| Ratios!X15 | Ratios\|15\|Ratios!r3 | Y19 | same_period | -Operation!W21 | Operation!W21 |
| Ratios!X16 | Ratios\|16\|Ratios!r3 | Y19 | same_period | 'P&L'!X23 | P&L!X23 |
| Ratios!X17 | Ratios\|17\|Ratios!r3 | Y19 | aggregation | SUM(X12:X16) | Ratios!X12:X16 |
| Ratios!X24 | Ratios\|24\|Ratios!r3 | Y19 | same_period | -Construction!W26 | Construction!W26 |
| Ratios!X25 | Ratios\|25\|Ratios!r3 | Y19 | same_period | -CFS!X21 | CFS!X21 |
| Ratios!X27 | Ratios\|27\|Ratios!r3 | Y19 | aggregation | SUM(X24:X26) | Ratios!X24:X26 |
| Ratios!X8 | Ratios\|8\|Ratios!r3 | Y19 | same_period | -Construction!W12 | Construction!W12 |
| Ratios!X9 | Ratios\|9\|Ratios!r3 | Y19 | same_period | -Construction!W13 | Construction!W13 |
| Ratios!Y10 | Ratios\|10\|Ratios!r3 | Y20 | same_period | -Construction!X14 | Construction!X14 |
| Ratios!Y11 | Ratios\|11\|Ratios!r3 | Y20 | same_period | -Construction!X15 | Construction!X15 |
| Ratios!Y12 | Ratios\|12\|Ratios!r3 | Y20 | aggregation | SUM(Y8:Y11) | Ratios!Y8:Y11 |
| Ratios!Y14 | Ratios\|14\|Ratios!r3 | Y20 | same_period | Operation!X14 | Operation!X14 |
| Ratios!Y15 | Ratios\|15\|Ratios!r3 | Y20 | same_period | -Operation!X21 | Operation!X21 |
| Ratios!Y16 | Ratios\|16\|Ratios!r3 | Y20 | same_period | 'P&L'!Y23 | P&L!Y23 |
| Ratios!Y17 | Ratios\|17\|Ratios!r3 | Y20 | aggregation | SUM(Y12:Y16) | Ratios!Y12:Y16 |
| Ratios!Y24 | Ratios\|24\|Ratios!r3 | Y20 | same_period | -Construction!X26 | Construction!X26 |
| Ratios!Y25 | Ratios\|25\|Ratios!r3 | Y20 | same_period | -CFS!Y21 | CFS!Y21 |
| Ratios!Y27 | Ratios\|27\|Ratios!r3 | Y20 | aggregation | SUM(Y24:Y26) | Ratios!Y24:Y26 |
| Ratios!Y8 | Ratios\|8\|Ratios!r3 | Y20 | same_period | -Construction!X12 | Construction!X12 |
| Ratios!Y9 | Ratios\|9\|Ratios!r3 | Y20 | same_period | -Construction!X13 | Construction!X13 |
| Ratios!Z10 | Ratios\|10\|Ratios!r3 | Y21 | same_period | -Construction!Y14 | Construction!Y14 |
| Ratios!Z11 | Ratios\|11\|Ratios!r3 | Y21 | same_period | -Construction!Y15 | Construction!Y15 |
| Ratios!Z12 | Ratios\|12\|Ratios!r3 | Y21 | aggregation | SUM(Z8:Z11) | Ratios!Z8:Z11 |
| Ratios!Z14 | Ratios\|14\|Ratios!r3 | Y21 | same_period | Operation!Y14 | Operation!Y14 |
| Ratios!Z15 | Ratios\|15\|Ratios!r3 | Y21 | same_period | -Operation!Y21 | Operation!Y21 |
| Ratios!Z16 | Ratios\|16\|Ratios!r3 | Y21 | same_period | 'P&L'!Z23 | P&L!Z23 |
| Ratios!Z17 | Ratios\|17\|Ratios!r3 | Y21 | aggregation | SUM(Z12:Z16) | Ratios!Z12:Z16 |
| Ratios!Z24 | Ratios\|24\|Ratios!r3 | Y21 | same_period | -Construction!Y26 | Construction!Y26 |
| Ratios!Z25 | Ratios\|25\|Ratios!r3 | Y21 | same_period | -CFS!Z21 | CFS!Z21 |
| Ratios!Z27 | Ratios\|27\|Ratios!r3 | Y21 | aggregation | SUM(Z24:Z26) | Ratios!Z24:Z26 |
| Ratios!Z8 | Ratios\|8\|Ratios!r3 | Y21 | same_period | -Construction!Y12 | Construction!Y12 |
| Ratios!Z9 | Ratios\|9\|Ratios!r3 | Y21 | same_period | -Construction!Y13 | Construction!Y13 |
| TBA!C10 | TBA\|10\|TBA!r2 |  | aggregation | SUM(D10:AQ10) | TBA!D10:AQ10 |
| TBA!C13 | TBA\|13\|TBA!r2 |  | aggregation | SUM(D13:AQ13) | TBA!D13:AQ13 |
| TBA!C14 | TBA\|14\|TBA!r2 |  | aggregation | SUM(D14:AQ14) | TBA!D14:AQ14 |
| TBA!C15 | TBA\|15\|TBA!r2 |  | aggregation | SUM(D15:AQ15) | TBA!D15:AQ15 |
| TBA!C17 | TBA\|17\|TBA!r2 |  | aggregation | SUM(D17:AQ17) | TBA!D17:AQ17 |
| TBA!C18 | TBA\|18\|TBA!r2 |  | aggregation | SUM(D18:AQ18) | TBA!D18:AQ18 |
| TBA!C19 | TBA\|19\|TBA!r2 |  | aggregation | SUM(D19:AQ19) | TBA!D19:AQ19 |
| TBA!C7 | TBA\|7\|TBA!r2 |  | aggregation | SUM(D7:AQ7) | TBA!D7:AQ7 |
| TBA!C8 | TBA\|8\|TBA!r2 |  | aggregation | SUM(D8:AQ8) | TBA!D8:AQ8 |
| TBA!C9 | TBA\|9\|TBA!r2 |  | aggregation | SUM(D9:AQ9) | TBA!D9:AQ9 |
