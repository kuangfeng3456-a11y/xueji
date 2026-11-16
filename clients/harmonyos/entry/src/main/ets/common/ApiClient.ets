import { http } from '@kit.NetworkKit';
import { common } from '@kit.AbilityKit';
import { fileIo } from '@kit.CoreFileKit';
import { readString, writeString } from './SessionStore';

export class ApiClient {
  context: common.UIAbilityContext;
  base: string = 'http://127.0.0.1:8000';
  token: string = '';
  goalId: string = '';

  constructor(context: common.UIAbilityContext) {
    this.context = context;
  }

  async load(): Promise<void> {
    this.base = await readString(this.context, 'apiBase', 'http://127.0.0.1:8000');
    this.token = await readString(this.context, 'token', '');
    this.goalId = await readString(this.context, 'goalId', '');
  }

  async saveBase(value: string): Promise<void> {
    const clean = value.trim().replace(/\/+$/, '');
    this.base = clean.length > 0 ? clean : 'http://127.0.0.1:8000';
    await writeString(this.context, 'apiBase', this.base);
  }

  async saveToken(token: string, nickname: string): Promise<void> {
    this.token = token;
    await writeString(this.context, 'token', token);
    await writeString(this.context, 'nickname', nickname);
  }

  async saveGoal(goalId: string): Promise<void> {
    this.goalId = goalId;
    await writeString(this.context, 'goalId', goalId);
  }

  url(path: string): string {
    const root = this.base.replace(/\/+$/, '');
    if (path.startsWith('http')) {
      return path;
    }
    if (path.startsWith('/api')) {
      return root + path;
    }
    const suffix = path.startsWith('/') ? path : '/' + path;
    return root + '/api' + suffix;
  }

  async request(method: http.RequestMethod, path: string, body?: string): Promise<string> {
    const client = http.createHttp();
    const header: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    if (this.token.length > 0) {
      header['Authorization'] = 'Bearer ' + this.token;
      header['X-Auth-Token'] = this.token;
    }
    try {
      const response = await client.request(this.url(path), {
        method: method,
        header: header,
        extraData: body,
        connectTimeout: 15000,
        readTimeout: 40000,
        expectDataType: http.HttpDataType.STRING
      });
      const text = this.asText(response.result);
      if (response.responseCode >= 400) {
        throw new Error(this.errorDetail(text, response.responseCode));
      }
      return text;
    } finally {
      client.destroy();
    }
  }

  async upload(path: string, filePath: string, fileName: string, contentType: string,
    fields: Record<string, string>): Promise<string> {
    const client = http.createHttp();
    const header: Record<string, string> = {};
    if (this.token.length > 0) {
      header['Authorization'] = 'Bearer ' + this.token;
      header['X-Auth-Token'] = this.token;
    }
    const parts: Array<http.MultiFormData> = [{
      name: 'file',
      contentType: contentType,
      filePath: filePath,
      remoteFileName: fileName
    }];
    const keys = Object.keys(fields);
    for (let i = 0; i < keys.length; i++) {
      const key = keys[i];
      parts.push({
        name: key,
        contentType: 'text/plain',
        data: fields[key]
      });
    }
    try {
      const response = await client.request(this.url(path), {
        method: http.RequestMethod.POST,
        header: header,
        multiFormDataList: parts,
        connectTimeout: 15000,
        readTimeout: 60000,
        expectDataType: http.HttpDataType.STRING
      });
      const text = this.asText(response.result);
      if (response.responseCode >= 400) {
        throw new Error(this.errorDetail(text, response.responseCode));
      }
      return text;
    } finally {
      client.destroy();
    }
  }

  async copyUriToCache(uri: string, fileName: string): Promise<string> {
    const dest = this.context.cacheDir + '/' + fileName;
    const source = fileIo.openSync(uri, fileIo.OpenMode.READ_ONLY);
    const target = fileIo.openSync(dest, fileIo.OpenMode.CREATE | fileIo.OpenMode.READ_WRITE | fileIo.OpenMode.TRUNC);
    const stat = fileIo.statSync(source.fd);
    const buffer = new ArrayBuffer(stat.size);
    fileIo.readSync(source.fd, buffer);
    fileIo.writeSync(target.fd, buffer);
    fileIo.closeSync(source);
    fileIo.closeSync(target);
    return dest;
  }

  asText(result: string | Object | ArrayBuffer): string {
    if (typeof result === 'string') {
      return result;
    }
    return JSON.stringify(result);
  }

  errorDetail(text: string, code: number): string {
    try {
      const data = JSON.parse(text) as ESObject;
      const detail = data['detail'];
      if (typeof detail === 'string' && detail.length > 0) {
        return detail;
      }
    } catch (err) {
      return '请求失败（' + code + '）';
    }
    return '请求失败（' + code + '）';
  }
}

export function readField(data: ESObject, key: string): string {
  const value = data[key];
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number') {
    return value.toString();
  }
  return '';
}
