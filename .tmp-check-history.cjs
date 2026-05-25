const fs = require('fs');
const lines = fs.readFileSync('apps/web/src/pages/HistoryPage.jsx', 'utf8').split(/\r?\n/);
const start = lines.findIndex((l) => l.includes('  return ('));
const end = lines.findIndex((l) => l.trim() === ');');
let count = 0;
let inString = null;
let escape = false;
let inLineComment = false;
let inBlockComment = false;
for (let i = start; i <= end; i++) {
  const line = lines[i];
  let delta = 0;
  for (let j = 0; j < line.length; j++) {
    const ch = line[j];
    const next = line[j + 1];
    if (inLineComment) break;
    if (inBlockComment) {
      if (ch === '*' && next === '/') {
        inBlockComment = false;
        j++;
      }
      continue;
    }
    if (inString) {
      if (escape) {
        escape = false;
        continue;
      }
      if (ch === '\\') {
        escape = true;
        continue;
      }
      if (ch === inString) inString = null;
      continue;
    }
    if (ch === '/' && next === '/') {
      inLineComment = true;
      break;
    }
    if (ch === '/' && next === '*') {
      inBlockComment = true;
      j++;
      continue;
    }
    if (ch === '"' || ch === '\'' || ch === '`') {
      inString = ch;
      continue;
    }
    if (ch === '(') {
      count++;
      delta++;
    } else if (ch === ')') {
      count--;
      delta--;
    }
  }
  if (line.includes('//')) inLineComment = false;
  console.log(String(i + 1).padStart(4), String(delta).padStart(3), String(count).padStart(3), line);
}
