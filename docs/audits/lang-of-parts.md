# Language-of-parts audit

The generated trace and report contain catalog copy in the selected document
language plus operator-authored titles, definitions, caveats, metric identifiers,
SQL, hashes, timestamps, and category values. SQL, identifiers, and hashes are
technical terms exempt from language-of-parts marking. Operator-authored prose
must match the selected locale; the tool does not infer its language.

No fixed catalog message embeds a foreign-language passage. The HTML root carries
`lang="en"` or `lang="es"`. If an operator intentionally embeds a foreign-language
passage in a title or definition, the current plain-text field cannot add a nested
`lang` span; the operator should avoid mixed-language prose or treat that as a
known limitation in the ACR.

Reviewed 2026-07-12 by Chelsea Kelly-Reif. Recheck each release and string change.
