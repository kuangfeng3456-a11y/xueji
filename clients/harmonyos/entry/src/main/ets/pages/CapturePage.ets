import { common } from '@kit.AbilityKit';
import { promptAction, router } from '@kit.ArkUI';
import { camera, cameraPicker } from '@kit.CameraKit';
import { picker } from '@kit.CoreFileKit';
import { http } from '@kit.NetworkKit';
import { ApiClient, readField } from '../common/ApiClient';
import { AppNav } from '../common/AppNav';

@Entry
@Component
struct CapturePage {
  @State question: string = '';
  @State note: string = '拍照或从相册选择。文字识别未开通时，请把题干补全后再保存。';
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
    }
  }

  async recognize(uri: string): Promise<void> {
    if (!this.client) {
      return;
    }
    this.busy = true;
    try {
      const path = await this.client.copyUriToCache(uri, 'mistake.jpg');
      const text = await this.client.upload('/cloud/ocr/extract', path, 'mistake.jpg', 'image/jpeg', {
        kind: 'general'
      });
      const data = JSON.parse(text) as ESObject;
      const status = readField(data, 'status');
      const recognized = readField(data, 'text');
      if (status === 'ok' && recognized.length > 0) {
        this.question = recognized;
        const detection = data['detection'] as ESObject;
        const regions = detection ? detection['regions'] as Array<ESObject> : [];
        this.note = regions && regions.length > 0 ? '已按题目区域识别，请核对后保存。' : '已识别题干，请核对后保存。';
      } else if (status === 'not_configured' || status === 'sdk_missing' || status === 'not_subscribed') {
        this.note = '文字识别未开通，请手动填写题干。照片仍可在核对后保存为错题。';
      } else {
        this.note = readField(data, 'detail').length > 0 ? readField(data, 'detail') : '这次没有识别出文字，请手动填写题干。';
      }
    } catch (err) {
      this.note = (err as Error).message;
    } finally {
      this.busy = false;
    }
  }

  async takePhoto(): Promise<void> {
    const context = getContext(this) as common.UIAbilityContext;
    try {
      const profile: cameraPicker.PickerProfile = {
        cameraPosition: camera.CameraPosition.CAMERA_POSITION_BACK
      };
      const result = await cameraPicker.pick(context, [cameraPicker.PickerMediaType.PHOTO], profile);
      if (result.resultCode === 0 && result.resultUri.length > 0) {
        await this.recognize(result.resultUri);
      }
    } catch (err) {
      this.note = '相机不可用：' + (err as Error).message;
    }
  }

  async pickAlbum(): Promise<void> {
    try {
      const photoPicker = new picker.PhotoViewPicker();
      const result = await photoPicker.select({
        MIMEType: picker.PhotoViewMIMETypes.IMAGE_TYPE,
        maxSelectNumber: 1
      });
      if (result.photoUris.length > 0) {
        await this.recognize(result.photoUris[0]);
      }
    } catch (err) {
      this.note = '相册不可用：' + (err as Error).message;
    }
  }

  async saveMistake(): Promise<void> {
    if (!this.client || this.question.trim().length === 0) {
      this.note = '请先填写或识别题干';
      return;
    }
    if (this.client.goalId.length === 0) {
      this.note = '还没有考试目标，请先在网页端创建。';
      return;
    }
    this.busy = true;
    try {
      await this.client.request(
        http.RequestMethod.POST,
        '/goals/' + this.client.goalId + '/mistakes',
        JSON.stringify({
          question: this.question.trim(),
          user_answer: '',
          correct_answer: '',
          source: 'photo'
        })
      );
      this.question = '';
      this.note = '已记入错题本。';
      promptAction.showToast({ message: '已保存错题' });
    } catch (err) {
      this.note = (err as Error).message;
    } finally {
      this.busy = false;
    }
  }

  build() {
    Column() {
      Scroll() {
        Column() {
          Text('拍题')
            .fontSize(28)
            .fontWeight(FontWeight.Bold)
          Text(this.note)
            .fontSize(14)
            .fontColor('#5C564C')
            .margin({ top: 8, bottom: 12 })
          Row({ space: 8 }) {
            Button(this.busy ? '处理中...' : '拍照')
              .layoutWeight(1)
              .backgroundColor('#1F6B4A')
              .enabled(!this.busy)
              .onClick(() => {
                this.takePhoto();
              })
            Button('相册')
              .layoutWeight(1)
              .backgroundColor('#E7E1D6')
              .fontColor('#1C1915')
              .enabled(!this.busy)
              .onClick(() => {
                this.pickAlbum();
              })
          }
          .width('100%')
          TextArea({ text: this.question, placeholder: '识别结果会出现在这里，也可以直接输入题干' })
            .width('100%')
            .height(180)
            .margin({ top: 16 })
            .onChange((value: string) => {
              this.question = value;
            })
          Button('保存到错题本')
            .width('100%')
            .margin({ top: 12 })
            .backgroundColor('#1F6B4A')
            .enabled(!this.busy)
            .onClick(() => {
              this.saveMistake();
            })
        }
        .padding(16)
        .alignItems(HorizontalAlign.Start)
      }
      .layoutWeight(1)

      AppNav({ current: 'capture' })
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#F6F3EC')
  }
}
