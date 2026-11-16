import { common } from '@kit.AbilityKit';
import { promptAction, router } from '@kit.ArkUI';
import { http } from '@kit.NetworkKit';
import { ApiClient, readField } from '../common/ApiClient';

@Entry
@Component
struct LoginPage {
  @State username: string = '';
  @State password: string = '';
  @State nickname: string = '';
  @State role: string = 'student';
  @State registerMode: boolean = false;
  @State hint: string = '';
  @State busy: boolean = false;
  private client: ApiClient | null = null;

  aboutToAppear(): void {
    this.boot();
  }

  async boot(): Promise<void> {
    const context = getContext(this) as common.UIAbilityContext;
    this.client = new ApiClient(context);
    await this.client.load();
    if (this.client.token.length > 0) {
      router.replaceUrl({ url: 'pages/TodayPage' });
    }
  }

  async submit(): Promise<void> {
    if (!this.client || this.busy) {
      return;
    }
    if (this.username.trim().length < 3 || this.password.length < 6) {
      this.hint = '用户名至少 3 位，密码至少 6 位';
      return;
    }
    this.busy = true;
    this.hint = '';
    try {
      const path = this.registerMode ? '/auth/register' : '/auth/login';
      const payload: Record<string, string> = {
        username: this.username.trim(),
        password: this.password
      };
      if (this.registerMode) {
        payload['nickname'] = this.nickname.trim().length > 0 ? this.nickname.trim() : this.username.trim();
        payload['role'] = this.role;
      }
      const text = await this.client.request(http.RequestMethod.POST, path, JSON.stringify(payload));
      const data = JSON.parse(text) as ESObject;
      const token = readField(data, 'access_token');
      const user = data['user'] as ESObject;
      const name = readField(user, 'nickname');
      if (token.length === 0) {
        this.hint = '登录没有返回凭证';
        return;
      }
      await this.client.saveToken(token, name);
      promptAction.showToast({ message: this.registerMode ? '注册成功' : '欢迎回来' });
      router.replaceUrl({ url: 'pages/TodayPage' });
    } catch (err) {
      this.hint = (err as Error).message;
    } finally {
      this.busy = false;
    }
  }

  build() {
    Column() {
      Text('学迹')
        .fontSize(36)
        .fontWeight(FontWeight.Bold)
        .fontColor('#1F6B4A')
        .margin({ top: 48 })
      Text('自适应学习教练')
        .fontSize(16)
        .fontColor('#5C564C')
        .margin({ top: 8, bottom: 28 })

      TextInput({ text: this.username, placeholder: '用户名' })
        .width('100%')
        .onChange((value: string) => {
          this.username = value;
        })
      TextInput({ text: this.password, placeholder: '密码' })
        .type(InputType.Password)
        .width('100%')
        .margin({ top: 12 })
        .onChange((value: string) => {
          this.password = value;
        })

      if (this.registerMode) {
        TextInput({ text: this.nickname, placeholder: '昵称，可选' })
          .width('100%')
          .margin({ top: 12 })
          .onChange((value: string) => {
            this.nickname = value;
          })
        Row({ space: 8 }) {
          this.roleButton('学生', 'student')
          this.roleButton('教师', 'teacher')
          this.roleButton('教务', 'academic')
        }
        .width('100%')
        .margin({ top: 12 })
        Text('教师和教务可以在网页端使用教师工作台。手机端仍是今天的学习路径。')
          .fontSize(12)
          .fontColor('#5C564C')
          .margin({ top: 8 })
      }

      Button(this.busy ? '处理中...' : (this.registerMode ? '注册并进入今日' : '登录'))
        .width('100%')
        .margin({ top: 20 })
        .backgroundColor('#1F6B4A')
        .enabled(!this.busy)
        .onClick(() => {
          this.submit();
        })
      Button(this.registerMode ? '已有账号，去登录' : '没有账号，去注册')
        .width('100%')
        .margin({ top: 8 })
        .backgroundColor('#E7E1D6')
        .fontColor('#1C1915')
        .onClick(() => {
          this.registerMode = !this.registerMode;
        })
      if (this.hint.length > 0) {
        Text(this.hint)
          .fontSize(13)
          .fontColor('#8A3B2C')
          .margin({ top: 16 })
      }
      Text('服务地址在「设置」里修改。真机请填写电脑的局域网地址。')
        .fontSize(12)
        .fontColor('#5C564C')
        .margin({ top: 24 })
    }
    .width('100%')
    .height('100%')
    .padding(24)
    .backgroundColor('#F6F3EC')
    .alignItems(HorizontalAlign.Start)
  }

  @Builder
  roleButton(label: string, value: string) {
    Button(label)
      .layoutWeight(1)
      .backgroundColor(this.role === value ? '#1F6B4A' : '#E7E1D6')
      .fontColor(this.role === value ? '#FFFFFF' : '#1C1915')
      .onClick(() => {
        this.role = value;
      })
  }
}
