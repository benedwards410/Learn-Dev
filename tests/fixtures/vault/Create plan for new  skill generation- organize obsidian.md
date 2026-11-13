
# Create plan for new skill generation- organize obsidian
## Desired goals

1. Keep obsidian organized - auto file into folders based. 
2. Generate file names and titles based on content 
3. Add at top of file: (all based on content in specific markdown) 
	1. Category or tag Basic description of content 
	2. Last modified date, created date (auto populated)
	3. How it was created? User? LLM? Both? 
	4. List any other files in obsidian that are associated or similar topics, tags or category 
4. Separate into multiple files if markdown has content that does not match (ie. Fantasy football appears in KCE file, or python chat content vs file types chunking. Explain how you would accomplish this? 
5. Add log of notes created modified snd filed with face and how to use for user to access 

## Plan (to review, revise and produce )

Create a skill called "obsidian-note-processor".

  

PURPOSE

Process Markdown notes from my Obsidian vault: update them, add frontmatter, and tell me where each one belongs. Return the file under the SAME filename so I can overwrite the original. Never create v2, final, or copy files.

  

TRIGGER

Use when I attach .md files (or a zip of them) and say "process", "clean up", "file this", "triage my vault", or "update this note".

  

RULES

1. One living note per topic. Edit in place and keep the filename.

2. Filenames are the note's title. No version words (v2, final, new).

3. Every note gets this frontmatter at the top:

   ---

   title:

   description:   (one plain-English line)

   status:        (draft | active | superseded | archived)

   updated:       (today's date)

   tags: []

   supersedes:    (optional)

   ---

4. Suggest one destination folder: 00-Inbox, 10-Projects, 20-Areas, 30-Reference, or 90-Archive.

5. If two files cover the same topic, keep the newer one as active, mark the older "superseded", and suggest 90-Archive. Never delete.

6. Preserve my wording and content. Change only what I asked, plus frontmatter. Keep [[wikilinks]], tags, and code blocks unchanged.

7. If you are unsure which file is current or which folder fits, put the question in the table. Do not guess.

8. Lead with the bottom line. No long explanations.

  

OUTPUT

A. A table: File | New title | Description | Status | Destination folder | Action (keep / merge / archive) | Reason

B. The updated files, returned under their original names.

C. A one-line change summary per file.

  

EXAMPLES

1. Single file

   Input: "process" + "kce notes final v2.md"

   Output: renamed "KCE Ops Notes.md", frontmatter added, status active, destination 20-Areas, one-line change summary.

  

2. Duplicate pair

   Input: "File types for parsing.md" and "Python.md" (same topic, one adds embedder.py)

   Output: the newer one is "active" in 30-Reference. The older one is "superseded" and goes to 90-Archive, with "supersedes" filled in.

  

3. Vault triage

   Input: a zip of 40 loose files plus "triage my vault"

   Output: the full table, then renamed files with frontmatter, grouped by destination folder.

  

4. Edit request

   Input: "process: add a plain-English summary at the top" + a technical note

   Output: the summary added, the rest untouched, frontmatter added.

  

EDGE CASES

- A file already has frontmatter: merge it, don't overwrite fields I set.

- A file has no clear topic: status draft, folder 00-Inbox, and ask me.

- A file is more than 80% code or data: keep the content verbatim and add frontmatter only.

Your generator.py already calls litellm, so this prompt makes the model fully configurable. Paste it in:

Update my RAG pipeline so litellm is the only model interface, and the model is chosen by config, not code.

  

CONTEXT

- generator.py already uses `litellm.completion` with `model`, `api_base`, `api_key`.

- Python 3.11+. Modules: parser.py, batch_processor.py, chunker.py, embedder.py, generator.py.

  

REQUIREMENTS

1. Add `config.yaml` with: model, api_base, api_key_env (the NAME of an env var, never the key itself), temperature, max_tokens, timeout, fallback_models (list).

2. Add `llm.py` with one function: `ask(messages, **overrides) -> str`.

   - Reads config.yaml and the API key from the environment.

   - Retries 3 times with backoff on rate-limit or timeout errors.

   - Tries each fallback model in order if the primary fails.

   - Logs model name, token usage, and latency. Never logs keys or document text.

3. Change generator.py to call `ask()` instead of calling `completion` directly. Behavior stays the same.

4. Make verification robust: if the verifier's JSON fails to parse, retry once with "Return ONLY valid JSON," then return `is_grounded: false` with an error note.

5. Add a `--model` CLI flag to run_pipeline.py that overrides config.

6. Add a smoke test: `python llm.py --test` sends "Reply with OK" and prints the model, the reply, and the latency.

  

MODEL STRINGS TO SUPPORT (as config examples)

- OpenAI:     model: gpt-4o-mini            key env: OPENAI_API_KEY

- Anthropic:  model: anthropic/claude-sonnet-4-5   key env: ANTHROPIC_API_KEY

- Ollama:     model: ollama/llama3, api_base: http://localhost:11434   (no key)

- LM Studio:  model: openai/local-model, api_base: http://localhost:1234/v1, api_key: "lm-studio"

  

PRIVACY

- Document text goes only to the configured model. If api_base is local, nothing leaves the machine. Print a warning at startup naming the destination (local or remote).

  

OUTPUT

Return complete files: config.yaml, llm.py, the updated generator.py, and a 5-line README on switching models. Then list how to verify it works.

  

EXAMPLES OF EXPECTED USE

- Switch to local: edit 2 lines in config.yaml, no code changes.

- One-off test: `python run_pipeline.py --model ollama/llama3`

- Provider outage: the pipeline falls back to the next model and logs it.

Replace the Anthropic model string with whichever current model ID you use, since litellm needs the exact name. For the local options, install Ollama or LM Studio first.

I can build these files and test them against a local model here if you want. Say go.