import { router } from '@kit.ArkUI';

@Component
export struct AppNav {
  @Prop current: string = 'today';

  build() {
    Row({ space: 8 }) {
      this.link('今日', 'pages/TodayPage', 'today')
      this.link('拍题', 'pages/CapturePage', 'capture')
      this.link('口语', 'pages/CoachPage', 'coach')
      this.link('复盘', 'pages/ReviewPage', 'review')
      this.link('设置', 'pages/SettingsPage', 'settings')
    }
    .width('100%')
    .padding({ left: 12, right: 12, top: 8, bottom: 12 })
  }

  @Builder
  link(label: string, url: string, key: string) {
    Button(label)
      .layoutWeight(1)
      .height(36)
      .fontSize(13)
      .backgroundColor(this.current === key ? '#1F6B4A' : '#E7E1D6')
      .fontColor(this.current === key ? '#FFFFFF' : '#1C1915')
      .onClick(() => {
        if (this.current !== key) {
          router.replaceUrl({ url: url });
        }
      })
  }
}
