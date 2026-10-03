// Generated domain-profile bridge: Node runs the same bundled Python validator,
// repairer and parser. Your async callback keeps its existing SDK and credentials.
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

export class WorkflowError extends Error {
  constructor(report) { super('.mini response could not be validated; no JSON was delivered'); this.report = report; }
}

export class Workflow {
  constructor({ lang, python = 'python' } = {}) { this.lang = lang; this.python = python; this.lastRun = null; }

  async prompt(task, expectedRecords) {
    const lang = this.lang || JSON.parse(await readFile(new URL('./setup.json', import.meta.url), 'utf8')).language;
    if (!['es', 'en'].includes(lang)) throw Error('lang must be es or en');
    const format = await readFile(new URL(`./prompt.${lang}.md`, import.meta.url), 'utf8');
    const count = expectedRecords === undefined ? '' : `\nRequired record count: ${expectedRecords}.`;
    return `Task / Tarea:\n${task}${count}\n\nOutput format (replaces JSON instructions):\n${format}`;
  }

  invoke(text, expectedRecords, correction) {
    const args = [fileURLToPath(new URL('./workflow.py', import.meta.url)), '-', '--envelope', '--report'];
    if (expectedRecords !== undefined) args.push('--expected-records', String(expectedRecords));
    return new Promise((resolve, reject) => {
      const child = spawn(this.python, args, { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
      let stdout = '', stderr = '';
      child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
      child.stdout.on('data', chunk => { stdout += chunk; });
      child.stderr.on('data', chunk => { stderr += chunk; });
      child.on('error', reject);
      child.on('close', code => {
        try {
          const report = JSON.parse(code === 0 ? stdout : stderr);
          this.lastRun = report;
          if (code === 0) resolve(report.data); else reject(new WorkflowError(report));
        } catch (error) { reject(error); }
      });
      child.stdin.on('error', reject);
      child.stdin.end(JSON.stringify({ text, correction }));
    });
  }

  async run(generate, task, { expectedRecords, maxRepairs = 1 } = {}) {
    if (![0, 1].includes(maxRepairs)) throw Error('maxRepairs must be 0 or 1');
    if (expectedRecords !== undefined && (!Number.isInteger(expectedRecords) || expectedRecords < 0)) throw Error('invalid expectedRecords');
    const prompt = await this.prompt(task, expectedRecords);
    const text = await generate(prompt);
    try { return await this.invoke(text, expectedRecords); }
    catch (error) {
      if (!(error instanceof WorkflowError) || maxRepairs === 0) throw error;
      const diagnostic = error.report.diagnostics;
      const request = `${prompt}\n\nOriginal response:\n${error.report.mini}\n\nCORRECTION REQUEST (overrides output format for this call):\n${diagnostic.repair_prompt}`;
      const correction = await generate(request);
      return this.invoke(text, expectedRecords, correction);
    }
  }
}
