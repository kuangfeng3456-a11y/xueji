import { common } from '@kit.AbilityKit';
import { router } from '@kit.ArkUI';
import { http } from '@kit.NetworkKit';
import { ApiClient, readField } from '../common/ApiClient';
import { AppNav } from '../common/AppNav';

@Entry
@Component
struct ReviewPage {
  @State summary: string = '正在读取复盘...';
  @State report: string = '';
  @State weak: string = '';
  @State hint: string = '';
  private client: ApiClient | null = null;

  aboutToAppear(): void {
    this.reload();
  }

  async reload(): Promise<void> {
    const context = getContext(this) as common.UIAbilityContext;
    this.client = new ApiClient(context);
    await this.client.load();
    if (this.client.token.length === 0) {
      router.replaceUrl({ url: 'pages/LoginPage' });
      return;
    }
    if (this.client.goalId.length === 0) {
      this.summary = '还没有考试目标。请先在网页端创建目标并完成今天的任务。';
      return;
    }
    try {
      const boardText = await this.client.request(
        http.RequestMethod.GET,
        '/dashboard?goal_id=' + this.client.goalId
      );
      const board = JSON.parse(boardText) as ESObject;
      this.summary = readField(board, 'coach_message');
      const mistakes = readField(board, 'mistake_count_7d');
      const points = board['weak_points'] as Array<ESObject>;
      const names: string[] = [];
      if (points) {
        for (let i = 0; i < points.length && i < 3; i++) {
          const name = readField(points[i], 'kp_name');
          if (name.length > 0) {
            names.push(name);
          }
        }
      }
      this.weak = names.length > 0 ? '近期薄弱点：' + names.join('、') : '还没有足够的掌握度数据。';
      this.summary = this.summary + '\n近 7 天错题 ' + (mistakes.length > 0 ? mistakes : '0') + ' 道。';
      try {
        const reportText = await this.client.request(
          http.RequestMethod.GET,
          '/goals/' + this.client.goalId + '/reports/latest'
        );
        if (reportText && reportText !== 'null') {
          const report = JSON.parse(reportText) as ESObject;
          this.report = readField(report, 'content');
          if (this.report.length === 0) {
            this.report = readField(report, 'focus');
          }
        } else {
          this.report = '还没有周报。在网页端生成周报后，这里会显示同一份内容。';
        }
      } catch (reportErr) {
        this.report = '还没有周报。完成一段时间的学习后再来看。';
      }
      this.hint = '';
    } catch (err) {
      this.hint = (err as Error).message;
    }
  }

  build() {
    Column() {
      Scroll() {
        Column() {
          Text('复盘')
            .fontSize(28)
            .fontWeight(FontWeight.Bold)
          Text(this.summary)
            .fontSize(15)
            .lineHeight(22)
            .margin({ top: 12 })
          Text(this.weak)
            .fontSize(15)
            .margin({ top: 12 })
          Text(this.report)
            .fontSize(14)
            .fontColor('#5C564C')
            .margin({ top: 12 })
          if (this.hint.length > 0) {
            Text(this.hint).fontSize(13).fontColor('#8A3B2C').margin({ top: 12 })
          }
          Button('刷新')
            .margin({ top: 16 })
            .backgroundColor('#E7E1D6')
            .fontColor('#1C1915')
            .onClick(() => {
              this.reload();
            })
        }
        .padding(16)
        .alignItems(HorizontalAlign.Start)
      }
      .layoutWeight(1)

      AppNav({ current: 'review' })
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#F6F3EC')
  }
}
