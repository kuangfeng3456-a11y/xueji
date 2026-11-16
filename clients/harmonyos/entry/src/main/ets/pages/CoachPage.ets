import { abilityAccessCtrl, common, Permissions } from '@kit.AbilityKit';
import { promptAction, router } from '@kit.ArkUI';
import { picker } from '@kit.CoreFileKit';
import { media } from '@kit.MediaKit';
import { http } from '@kit.NetworkKit';
import { speechRecognizer, textToSpeech } from '@kit.CoreSpeechKit';
import { util } from '@kit.ArkTS';
import { fileIo, fileUri } from '@kit.CoreFileKit';
import { ApiClient, readField } from '../common/ApiClient';
import { AppNav } from '../common/AppNav';

interface ChatLine {
  id: string;
  role: string;
  text: string;
}

@Entry
@Component
struct CoachPage {
  @State lines: ChatLine[] = [];
  @State draft: string = '';
  @State note: string = '连续提问会记住本轮上下文。云端语音未开通时，请使用本机听写或文字。';
  @State sessionId: string = '';
  @State busy: boolean = false;
  private client: ApiClient | null = null;

  aboutToAppear(): void {
    this.prepare();
  }

  async prepare(): Promise<void> {
    const context = getContext(this) as common.UIAbilityContext;
    this.client = new ApiClient(context);
    await this.client.load();
    if (this.client.token.length === 0) {
      router.replaceUrl({ url: 'pages/LoginPage' });
      return;
    }
    try {
      const listed = JSON.parse(await this.client.request(http.RequestMethod.GET, '/coach/sessions')) as ESObject;
      const items = listed['items'] as Array<ESObject>;
      if (items && items.length > 0) {
        this.sessionId = readField(items[0], 'id');
        await this.loadMessages();
        return;
      }
    } catch (err) {
      this.note = (err as Error).message;
    }
    await this.openSession();
  }

  async openSession(): Promise<void> {
    if (!this.client) {
      return;
    }
    let body = '{"title":"语音教练"}';
    if (this.client.goalId.length > 0) {
      body = '{"title":"语音教练","goal_id":' + this.client.goalId + '}';
    }
    const text = await this.client.request(http.RequestMethod.POST, '/coach/sessions', body);
    const data = JSON.parse(text) as ESObject;
    this.sessionId = readField(data, 'id');
  }

  async loadMessages(): Promise<void> {
    if (!this.client || this.sessionId.length === 0) {
      return;
    }
    const text = await this.client.request(http.RequestMethod.GET, '/coach/sessions/' + this.sessionId);
    const data = JSON.parse(text) as ESObject;
    const messages = data['messages'] as Array<ESObject>;
    const next: ChatLine[] = [];
    if (messages) {
      for (let i = 0; i < messages.length; i++) {
        next.push({
          id: readField(messages[i], 'id'),
          role: readField(messages[i], 'role'),
          text: readField(messages[i], 'text')
        });
      }
    }
    this.lines = next;
  }

  async sendText(content: string): Promise<void> {
    if (!this.client || content.trim().length === 0 || this.busy) {
      return;
    }
    if (this.sessionId.length === 0) {
      await this.openSession();
    }
    this.busy = true;
    try {
      const escaped = content.trim().replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n');
      let payload = '{"text":"' + escaped + '"}';
      if (this.client.goalId.length > 0) {
        payload = '{"text":"' + escaped + '","goal_id":' + this.client.goalId + '}';
      }
      const text = await this.client.request(
        http.RequestMethod.POST,
        '/coach/sessions/' + this.sessionId + '/messages',
        payload
      );
      const data = JSON.parse(text) as ESObject;
      this.draft = '';
      await this.loadMessages();
      const answer = readField(data, 'answer');
      if (answer.length > 0) {
        await this.speak(answer);
      }
    } catch (err) {
      this.note = (err as Error).message;
    } finally {
      this.busy = false;
    }
  }

  async listenOnDevice(): Promise<void> {
    const context = getContext(this) as common.UIAbilityContext;
    const allowed = await this.grant(context, ['ohos.permission.MICROPHONE']);
    if (!allowed) {
      this.note = '没有麦克风权限，请改用文字。';
      return;
    }
    try {
      const engine = await speechRecognizer.createEngine({
        language: 'zh-CN',
        online: 1
      });
      const sessionId = 'xueji' + Date.now().toString();
      const heard = await new Promise<string>((resolve, reject) => {
        engine.setListener({
          onStart: () => {},
          onEvent: () => {},
          onResult: (_id: string, result: speechRecognizer.SpeechRecognitionResult) => {
            if (result.isLast && result.result.length > 0) {
              resolve(result.result);
            }
          },
          onComplete: () => {},
          onError: (_id: string, code: number, message: string) => {
            reject(new Error(message.length > 0 ? message : '本机语音识别失败 ' + code));
          }
        });
        engine.startListening({
          sessionId: sessionId,
          audioInfo: { audioType: 'pcm', sampleRate: 16000, soundChannel: 1, sampleBit: 16 }
        });
        setTimeout(() => {
          engine.finish(sessionId);
        }, 5000);
      });
      this.note = '本机听写';
      await this.sendText(heard);
    } catch (err) {
      this.note = '本机语音不可用：' + (err as Error).message + '。可上传录音走云端识别，或直接输入文字。';
    }
  }

  async uploadAudio(): Promise<void> {
    if (!this.client) {
      return;
    }
    try {
      const documentPicker = new picker.DocumentViewPicker();
      const result = await documentPicker.select({
        maxSelectNumber: 1
      });
      if (result.length === 0) {
        return;
      }
      if (this.sessionId.length === 0) {
        await this.openSession();
      }
      const cached = await this.client.copyUriToCache(result[0], 'speech.wav');
      const fields: Record<string, string> = { audio_format: 'wav' };
      if (this.client.goalId.length > 0) {
        fields['goal_id'] = this.client.goalId;
      }
      const text = await this.client.upload(
        '/coach/sessions/' + this.sessionId + '/voice',
        cached,
        'speech.wav',
        'audio/wav',
        fields
      );
      const data = JSON.parse(text) as ESObject;
      const status = readField(data, 'status');
      if (status === 'ok') {
        this.note = '云端语音识别';
        await this.loadMessages();
        const answer = readField(data, 'answer');
        if (answer.length > 0) {
          await this.speak(answer);
        }
        return;
      }
      this.note = readField(data, 'fallback_label').length > 0
        ? readField(data, 'fallback_label')
        : '云端语音识别不可用，请改用本机听写或文字';
    } catch (err) {
      this.note = (err as Error).message;
    }
  }

  async speak(content: string): Promise<void> {
    if (!this.client) {
      return;
    }
    try {
      const client = http.createHttp();
      const header: Record<string, string> = {};
      header['Authorization'] = 'Bearer ' + this.client.token;
      header['X-Auth-Token'] = this.client.token;
      const parts: Array<http.MultiFormData> = [{
        name: 'text',
        contentType: 'text/plain',
        data: content.slice(0, 500)
      }];
      const response = await client.request(this.client.url('/cloud/sis/synthesize'), {
        method: http.RequestMethod.POST,
        header: header,
        multiFormDataList: parts,
        expectDataType: http.HttpDataType.STRING
      });
      client.destroy();
      const data = JSON.parse(this.client.asText(response.result)) as ESObject;
      const audio = readField(data, 'audio_b64');
      if (readField(data, 'status') === 'ok' && audio.length > 0) {
        await this.playBase64(audio);
        this.note = '云端语音合成';
        return;
      }
      this.note = readField(data, 'fallback_label').length > 0 ? readField(data, 'fallback_label') : '改用本机朗读';
    } catch (err) {
      this.note = '改用本机朗读';
    }
    await this.speakOnDevice(content);
  }

  async playBase64(audio: string): Promise<void> {
    if (!this.client) {
      return;
    }
    const helper = new util.Base64Helper();
    const bytes = helper.decodeSync(audio);
    const path = this.client.context.cacheDir + '/coach.mp3';
    const file = fileIo.openSync(path, fileIo.OpenMode.CREATE | fileIo.OpenMode.READ_WRITE | fileIo.OpenMode.TRUNC);
    fileIo.writeSync(file.fd, bytes.buffer);
    fileIo.closeSync(file);
    const player = await media.createAVPlayer();
    player.url = fileUri.getUriFromPath(path);
    player.play();
  }

  async speakOnDevice(content: string): Promise<void> {
    try {
      const engine = await textToSpeech.createEngine({ language: 'zh-CN', online: 1 });
      engine.speak(content, { requestId: 'tts' + Date.now().toString() });
    } catch (err) {
      promptAction.showToast({ message: '本机朗读不可用，请阅读文字回复' });
    }
  }

  async grant(context: common.UIAbilityContext, permissions: Array<Permissions>): Promise<boolean> {
    const manager = abilityAccessCtrl.createAtManager();
    const result = await manager.requestPermissionsFromUser(context, permissions);
    for (let i = 0; i < result.authResults.length; i++) {
      if (result.authResults[i] !== 0) {
        return false;
      }
    }
    return true;
  }

  build() {
    Column() {
      Scroll() {
        Column() {
          Text('口语教练')
            .fontSize(28)
            .fontWeight(FontWeight.Bold)
          Text(this.note)
            .fontSize(13)
            .fontColor('#5C564C')
            .margin({ top: 8, bottom: 12 })
          if (this.lines.length === 0) {
            Text('可以直接问「今天学什么」，下一句再说「为什么」，教练会接上一次的回答。')
              .fontSize(14)
              .fontColor('#5C564C')
          }
          ForEach(this.lines, (line: ChatLine) => {
            Text((line.role === 'user' ? '我：' : '教练：') + line.text)
              .fontSize(15)
              .width('100%')
              .padding(12)
              .margin({ bottom: 8 })
              .backgroundColor(line.role === 'user' ? '#E7F2EB' : '#FFFFFF')
              .borderRadius(12)
          }, (line: ChatLine) => line.id)
          TextInput({ text: this.draft, placeholder: '输入问题' })
            .width('100%')
            .margin({ top: 8 })
            .onChange((value: string) => {
              this.draft = value;
            })
          Row({ space: 8 }) {
            Button('发送')
              .layoutWeight(1)
              .backgroundColor('#1F6B4A')
              .enabled(!this.busy)
              .onClick(() => {
                this.sendText(this.draft);
              })
            Button('本机听写')
              .layoutWeight(1)
              .backgroundColor('#E7E1D6')
              .fontColor('#1C1915')
              .onClick(() => {
                this.listenOnDevice();
              })
          }
          .width('100%')
          .margin({ top: 8 })
          Button('上传录音做云端识别')
            .width('100%')
            .margin({ top: 8 })
            .backgroundColor('#E7E1D6')
            .fontColor('#1C1915')
            .onClick(() => {
              this.uploadAudio();
            })
        }
        .padding(16)
        .alignItems(HorizontalAlign.Start)
      }
      .layoutWeight(1)

      AppNav({ current: 'coach' })
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#F6F3EC')
  }
}
