from pathlib import Path
for name in ['种子.md','种子代表集_18条_垂直正交.md','关键证据.md','种子交付前自查.md']:
    b=(Path(r'D:\DeskTop\my_benchmark\AAA_core_data')/name).read_bytes()
    print(name, 'CRLF', b.count(b'\r\n'), 'LF', b.count(b'\n'))
