"""Small brace-aware parser for the project's braced BibTeX records."""
from __future__ import annotations
import re
from pathlib import Path

def parse_bib(text):
    entries=[]
    for match in re.finditer(r'@(\w+)\s*\{\s*([^,]+),',text):
        pos=match.end();start=pos;depth=1
        while pos<len(text) and depth:
            if text[pos]=='{' and text[pos-1]!='\\':depth+=1
            elif text[pos]=='}' and text[pos-1]!='\\':depth-=1
            pos+=1
        body=text[start:pos-1];fields={};j=0
        while j<len(body):
            m=re.search(r'(\w+)\s*=\s*',body[j:])
            if not m:break
            key=m[1].lower();j+=m.end()
            if body[j]=='{':
                end=j+1;d=1
                while end<len(body) and d:
                    if body[end]=='{' and body[end-1]!='\\':d+=1
                    elif body[end]=='}' and body[end-1]!='\\':d-=1
                    end+=1
                fields[key]=body[j+1:end-1];j=end
            elif body[j]=='"':
                end=j+1
                while end<len(body) and body[end]!='"':end+=1
                fields[key]=body[j+1:end];j=end+1
            else:
                end=body.find(',',j);end=end if end>=0 else len(body)
                fields[key]=body[j:end].strip();j=end+1
        entries.append({'type':match[1].lower(),'key':match[2],**fields})
    return entries

def write_bib(entries,path):
    parts=[]
    for e in entries:
        parts.append('@'+e['type']+'{'+e['key']+',\n'+',\n'.join('  '+k+' = {'+str(v)+'}' for k,v in e.items() if k not in {'type','key'})+'\n}\n')
    Path(path).write_text('\n'.join(parts),encoding='utf-8')
