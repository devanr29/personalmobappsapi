"""AI layer over the budget ledger: explains and analyzes, never computes
or writes. facts.py turns already-computed numbers into short sentences
(pure, no LLM), llm.py has the model phrase a chosen subset of them and
rejects any reply quoting a figure the facts don't contain, and qa.py
answers free-form questions by mapping them onto a fixed menu of
read-only queries."""
