// Generated domain-profile bridge: Node runs the same bundled Python validator,
// repairer and parser. Your async callback keeps its existing SDK and credentials.
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

export class WorkflowError extends Error {
  constructor(report) { super('.mini response could not be validated; no JSON was delivered'); this.report = report; }
}

export class Workflow {
  constructor({ lang, python = 'python', promptStyle = 'full', kvCacheFirst = false } = {}) {
    this.lang = lang;
    this.python = python;
    this.promptStyle = promptStyle;
    this.kvCacheFirst = Boolean(kvCacheFirst);
    this.lastRun = null;
  }

  async prompt(task, expectedRecords, lastTextField) {
    const lang = this.lang || JSON.parse(await readFile(new URL('./setup.json', import.meta.url), 'utf8')).language;
    if (!['es', 'en'].includes(lang)) throw Error('lang must be es or en');
    if (lastTextField !== undefined) {
      const result = await this.runParser(['--rows-prompt', '--lang', lang, `--last-text-field=${lastTextField}`,
        '--expected-records', String(expectedRecords)], task);
      if (result.code !== 0) throw Error(result.stderr.trim());
      return result.stdout;
    }
    const promptFile = this.promptStyle === 'lean' ? `./prompt.lean.${lang}.md` : `./prompt.${lang}.md`;
    const format = await readFile(new URL(promptFile, import.meta.url), 'utf8').catch(
      () => readFile(new URL(`./prompt.${lang}.md`, import.meta.url), 'utf8'),
    );
    const count = expectedRecords === undefined ? '' : `\nRequired record count: ${expectedRecords}.`;
    if (this.kvCacheFirst) {
      return `Output format (replaces JSON instructions):\n${format}\n\nTask / Tarea:\n${task}${count}`;
    }
    return `Task / Tarea:\n${task}${count}\n\nOutput format (replaces JSON instructions):\n${format}`;
  }

  runParser(args, input) {
    const script = fileURLToPath(new URL('./workflow.py', import.meta.url));
    return new Promise((resolve, reject) => {
      const child = spawn(this.python, [script, '-', ...args], { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
      let stdout = '', stderr = '';
      child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
      child.stdout.on('data', chunk => { stdout += chunk; });
      child.stderr.on('data', chunk => { stderr += chunk; });
      child.on('error', reject);
      child.on('close', code => resolve({ code, stdout, stderr }));
      child.stdin.on('error', reject);
      child.stdin.end(input);
    });
  }

  async invoke(text, expectedRecords, correction, lastTextField, positionalJson = false) {
    const args = ['--envelope', '--report'];
    if (expectedRecords !== undefined) args.push('--expected-records', String(expectedRecords));
    if (lastTextField !== undefined) {
      args.push(`--last-text-field=${lastTextField}`);
    }
    if (positionalJson) args.push('--positional-json');
    if ((lastTextField !== undefined || positionalJson) && this.lang) args.push('--lang', this.lang);
    const { code, stdout, stderr } = await this.runParser(args, JSON.stringify({ text, correction }));
    const report = JSON.parse(code === 0 ? stdout : stderr);
    this.lastRun = report;
    if (code !== 0) throw new WorkflowError(report);
    return report.data;
  }

  async run(generate, task, { expectedRecords, maxRepairs = 1, lastTextField } = {}) {
    if (![0, 1].includes(maxRepairs)) throw Error('maxRepairs must be 0 or 1');
    if (expectedRecords !== undefined && (!Number.isInteger(expectedRecords) || expectedRecords < 0)) throw Error('invalid expectedRecords');
    if (lastTextField !== undefined && (typeof lastTextField !== 'string' || expectedRecords === undefined)) {
      throw Error('compact rows require lastTextField and expectedRecords');
    }
    const prompt = await this.prompt(task, expectedRecords, lastTextField);
    return this.generateAndValidate(generate, prompt, { expectedRecords, maxRepairs, lastTextField });
  }

  async runPositional(generate, task, { expectedRecords, maxRepairs = 1 } = {}) {
    if (![0, 1].includes(maxRepairs)) throw Error('maxRepairs must be 0 or 1');
    if (!Number.isInteger(expectedRecords) || expectedRecords < 0) throw Error('invalid expectedRecords');
    const args = ['--positional-request', '--expected-records', String(expectedRecords)];
    if (this.lang) args.push('--lang', this.lang);
    const result = await this.runParser(args, task);
    if (result.code !== 0) throw Error(result.stderr.trim());
    const { prompt, schema } = JSON.parse(result.stdout);
    return this.generateAndValidate(request => generate(request, schema), prompt,
      { expectedRecords, maxRepairs, positionalJson: true });
  }

  async generateAndValidate(generate, prompt, { expectedRecords, maxRepairs, lastTextField, positionalJson = false }) {
    const text = await generate(prompt);
    try { return await this.invoke(text, expectedRecords, undefined, lastTextField, positionalJson); }
    catch (error) {
      if (!(error instanceof WorkflowError) || maxRepairs === 0) throw error;
      const diagnostic = error.report.diagnostics;
      const request = lastTextField === undefined && !positionalJson
        ? `${prompt}\n\nOriginal response:\n${error.report.mini}\n\nCORRECTION REQUEST (overrides output format for this call):\n${diagnostic.repair_prompt}`
        : `${prompt}\n${diagnostic.repair_prompt}`;
      const correction = await generate(request);
      return this.invoke(text, expectedRecords, correction, lastTextField, positionalJson);
    }
  }
}
