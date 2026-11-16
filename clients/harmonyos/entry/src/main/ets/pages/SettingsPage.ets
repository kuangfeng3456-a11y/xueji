import { common } from '@kit.AbilityKit';
import { promptAction, router } from '@kit.ArkUI';
import { http } from '@kit.NetworkKit';
import { ApiClient } from '../common/ApiClient';
import { clearSession, readString } from '../common/SessionStore';
import { AppNav } from '../common/AppNav';

@Entry
@Component
struct SettingsPage {
  @State apiBase: string = 'http://127.0.0.1:8000';
  @State nickname: string = '';
  @State hint: string = '真机调试时，把地址改成运行学迹服务的电脑局域网地址，例如 http://192.168.1.20:8000。不要在这里填写密钥。';
  private client: ApiClient | null = null;

  aboutToAppear(): void {
    this.prepare();
  }

  async prepare(): Promise<void> {
    const context = getContext(this) as common.UIAbilityContext;
    this.client = new ApiClient(context);
    await this.client.load();
    this.apiBase = this.client.base;
    this.nickname = await readString(context, 'nickname', '');
    if (this.client.token.length === 0) {
      router.replaceUrl({ url: 'pages/LoginPage' });
    }
  }

  async save(): Promise<void> {
    if (!this.client) {
      return;
    }
    await this.client.saveBase(this.apiBase);
    this.apiBase = this.client.base;
    promptAction.showToast({ message: '已保存服务地址' });
  }

  async logout(): Promise<void> {
    if (!this.client) {
      return;
    }
    try {
      await this.client.request(http.RequestMethod.POST, '/auth/logout', '{}');
    } catch (err) {
      this.hint = '本地登录状态已清除';
    }
    await clearSession(this.client.context);
    router.replaceUrl({ url: 'pages/LoginPage' });
  }

  build() {
    Column() {
      Scroll() {
        Column() {
          Text('设置')
            .fontSize(28)
            .fontWeight(FontWeight.Bold)
          if (this.nickname.length > 0) {
            Text('当前账号：' + this.nickname)
              .fontSize(14)
              .fontColor('#5C564C')
              .margin({ top: 8 })
          }
          Text('服务地址')
            .fontSize(14)
            .margin({ top: 20, bottom: 8 })
          TextInput({ text: this.apiBase, placeholder: 'http://127.0.0.1:8000' })
            .width('100%')
            .onChange((value: string) => {
              this.apiBase = value;
            })
          Text(this.hint)
            .fontSize(13)
            .fontColor('#5C564C')
            .margin({ top: 8 })
          Button('保存地址')
            .width('100%')
            .margin({ top: 16 })
            .backgroundColor('#1F6B4A')
            .onClick(() => {
              this.save();
            })
          Button('退出登录')
            .width('100%')
            .margin({ top: 8 })
            .backgroundColor('#E7E1D6')
            .fontColor('#1C1915')
            .onClick(() => {
              this.logout();
            })
          Text('拍照、语音和朗读都调用同一套学习服务。云端文字识别或语音未开通时，页面会说明并改用手动输入或本机能力，不会显示虚构的识别结果。')
            .fontSize(13)
            .fontColor('#5C564C')
            .margin({ top: 20 })
        }
        .padding(16)
        .alignItems(HorizontalAlign.Start)
      }
      .layoutWeight(1)

      AppNav({ current: 'settings' })
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#F6F3EC')
  }
}
