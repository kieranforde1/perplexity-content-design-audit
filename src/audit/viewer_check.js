// The "Test a line of copy" box on the Check tab. This is a JavaScript copy of the rules in
// skill_check_text.py, which is what the pplx-content skill ships. A test runs both on the
// same sentences and fails if they ever disagree, so change the two files together.
// `audit view` pastes this file into the viewer, so it can't contain a closing script tag.
function checkText(text, entries, company) {
  "use strict";

  // A capital straight after one of these starts a sentence, so it isn't a wrong capital.
  var SENTENCE_BREAK = /[.!?:;"'“(\[]\s*$/;
  // Markdown list markers and headings come before the string itself.
  var MARKER = /^\s*(?:#+|[-*>]|\d+[.)])\s+/;
  var CODE = /`[^`]*`/g;

  function escapeRegex(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function words(s) { return s.split(/\s+/).filter(Boolean); }
  function upperFirst(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  function stripCompany(list) {
    if (list.length > 1 && list[0].toLowerCase() === company.toLowerCase()) return list.slice(1);
    return list;
  }

  // The parts of a form that make it a variant: case, spaces and hyphens. A plural or the
  // company name in front is normal grammar, so both go.
  function shape(form) {
    var t = stripCompany(words(form)).join(" ");
    if (t.length > 3 && t.slice(-1) === "s" && t.slice(-2) !== "ss") t = t.slice(0, -1);
    return t;
  }

  function patternFor(term) {
    var list = stripCompany(words(term.replace(/-/g, " ")));
    var last = list[list.length - 1];
    if (last.length > 3 && last.slice(-1) === "s") list[list.length - 1] = last.slice(0, -1);
    var body = list.map(escapeRegex).join("[\\s-]?");
    return new RegExp("\\b(?:" + escapeRegex(company) + "\\s+)?" + body + "(?:es|s)?\\b", "gi");
  }

  // A match inside a file name, URL or code ID ("sonar-pro") isn't prose.
  function insideIdentifier(t, start, end) {
    var before = start > 0 ? t.charAt(start - 1) : "";
    var after = end < t.length ? t.charAt(end) : "";
    var afterNext = end + 1 < t.length ? t.charAt(end + 1) : "";
    var matched = t.slice(start, end);
    return (
      (before !== "" && "-_/.".indexOf(before) !== -1) ||
      (after !== "" && "-_/".indexOf(after) !== -1) ||
      (after === "." && /[\p{L}\p{N}]/u.test(afterNext)) ||
      (matched.indexOf("-") !== -1 && matched === matched.toLowerCase())
    );
  }

  function isPlural(form) {
    var list = words(form.replace(/['’]s$/, ""));
    var last = list.length ? list[list.length - 1] : "";
    return last.length > 3 && last.slice(-1) === "s" && last.slice(-2) !== "ss";
  }

  function squash(s) { return s.replace(/[\s-]/g, "").toLowerCase(); }

  // "" if a use of a term to use is fine here, or the kind of variant it is.
  function spellingProblem(term, form, t, start, heading) {
    var written = shape(form);
    if (written === written.toLowerCase() && term !== term.toLowerCase()) return "";
    if (written.length > 1 && written === written.toUpperCase() && term !== term.toUpperCase()) return "";
    // "AI Assistant" names one thing. It isn't a variant of the plural term "AI assistants".
    if (isPlural(term) && !isPlural(form)) return "";
    var base = shape(term);
    var allowed = [base];
    if (start === 0 || SENTENCE_BREAK.test(t.slice(0, start))) allowed.push(upperFirst(base));
    if (heading) allowed.push(words(base).map(upperFirst).join(" "));
    var lowered = allowed.map(function (a) { return a.toLowerCase(); });
    // "Pro Searches" loses only its "s" in shape(), leaving "Pro Searche".
    if (written.slice(-1) === "e" && lowered.indexOf(written.slice(0, -1).toLowerCase()) !== -1) {
      written = written.slice(0, -1);
    }
    if (allowed.indexOf(written) !== -1) return "";
    if (lowered.indexOf(written.toLowerCase()) !== -1) return "capitalisation";
    var squashed = allowed.map(squash);
    if (squashed.indexOf(squash(written)) !== -1) return "spelling or spacing";
    return "other variant";
  }

  var patterns = {};
  entries.forEach(function (e) { patterns[e.term] = patternFor(e.term); });

  function matchesOf(term, t) {
    var re = patterns[term];
    re.lastIndex = 0;
    var found = [];
    var m;
    while ((m = re.exec(t)) !== null) {
      found.push({ start: m.index, end: m.index + m[0].length, form: m[0] });
    }
    return found;
  }

  var lines = text.split(/\r\n|[\r\n\u000b\u000c\u001c-\u001e\u0085\u2028\u2029]/);
  // Like Python's splitlines(), a final line break doesn't start another line.
  if (lines.length && lines[lines.length - 1] === "") lines.pop();

  var found = [];
  lines.forEach(function (raw, index) {
    var marker = MARKER.exec(raw);
    var offset = marker ? marker[0].length : 0;
    var heading = raw.replace(/^\s+/, "").charAt(0) === "#";
    // Blank out code so its offsets still line up with the line as written.
    var t = raw.slice(offset).replace(CODE, function (c) { return new Array(c.length + 1).join(" "); });
    entries.forEach(function (entry) {
      var term = entry.term;
      var status = entry.status;
      // A longer glossary term that contains this one ("API Portal" holds "portal")
      // already reports those words, so they aren't reported twice.
      var longer = [];
      entries.forEach(function (other) {
        if (other.term.length > term.length && other.term.toLowerCase().indexOf(term.toLowerCase()) !== -1) {
          matchesOf(other.term, t).forEach(function (m) { longer.push(m); });
        }
      });
      matchesOf(term, t).forEach(function (m) {
        var form = m.form;
        if (insideIdentifier(t, m.start, m.end)) return;
        var kind;
        var fix;
        if (status === "avoid" || status === "deprecated") {
          if (longer.some(function (l) { return l.start <= m.start && m.end <= l.end; })) return;
          if (status === "deprecated" && form === form.toLowerCase() && term !== term.toLowerCase()) return;
          kind = status === "deprecated" ? "deprecated name" : "avoided term";
          var replacement = (entry.use_instead || "").trim();
          fix = replacement ? "Use '" + replacement + "' instead." : "Reword without '" + term + "'.";
        } else {
          kind = spellingProblem(term, form, t, m.start, heading);
          if (!kind) return;
          fix = "Write '" + term + "'.";
        }
        found.push({
          line: index + 1,
          column: offset + m.start + 1,
          length: m.end - m.start,
          term: term,
          rule: kind + " '" + form + "'. " + fix
        });
      });
    });
  });

  found.sort(function (a, b) {
    if (a.line !== b.line) return a.line - b.line;
    if (a.column !== b.column) return a.column - b.column;
    if (a.term !== b.term) return a.term < b.term ? -1 : 1;
    return a.rule < b.rule ? -1 : a.rule > b.rule ? 1 : 0;
  });
  return { lines: lines, problems: found };
}

// Up to three sample strings for the box, taken from the Check tab's glossary rules, so
// every sample is published text the audit found, not invented copy. One per kind of
// rule where it can, the shortest string in each, and only strings checkText flags.
// A sample has to read as copy on its own: one word ("Enable") or code ("search_type")
// doesn't show a visitor anything.
function readsAsCopy(text) {
  return text.split(/\s+/).filter(Boolean).length >= 4 && !/[_`{}<>]/.test(text);
}

function sampleLines(rules, entries, company) {
  "use strict";
  var picked = [];
  var kinds = [];
  rules.forEach(function (rule) {
    if (picked.length >= 3 || rule.standard_id.indexOf("glossary:") !== 0) return;
    if (kinds.indexOf(rule.kind) !== -1) return;
    var texts = rule.strings.map(function (s) {
      return s.parts.map(function (part) { return part[0]; }).join("");
    }).filter(function (text) {
      return readsAsCopy(text) && checkText(text, entries, company).problems.some(function (p) { return p.term === rule.term; });
    }).sort(function (a, b) { return a.length - b.length; });
    if (!texts.length) return;
    picked.push(texts[0]);
    kinds.push(rule.kind);
  });
  return picked;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { checkText: checkText, sampleLines: sampleLines };
}
