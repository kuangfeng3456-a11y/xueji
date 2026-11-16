import { common } from '@kit.AbilityKit';
import { router } from '@kit.ArkUI';
import { http } from '@kit.NetworkKit';
import { ApiClient, readField } from '../common/ApiClient';
import { AppNav } from '../common/AppNav';

interface TaskItem {
  id: string;
  title: string;
  minutes: string;
  status: string;
  reason: string;
}

@Entry
@Component
struct TodayPage {
  @State examName: string = '还没有考试目标';
  @State coach: string = '正在读取今天的安排...';
  @State tasks: TaskItem[] = [];
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
    try {
      const goalsText = await this.client.request(http.RequestMethod.GET, '/goals');
      const goals = JSON.parse(goalsText) as Array<ESObject>;
      if (goals.length === 0) {
        this.examName = '还没有考试目标';
        this.coach = '请先在网页端创建考试目标，手机端会同步今天的任务。';
        this.tasks = [];
        return;
      }
      const goal = goals[0];
      const goalId = readField(goal, 'id');
      await this.client.saveGoal(goalId);
      this.examName = readField(goal, 'exam_name');
      const boardText = await this.client.request(http.RequestMethod.GET, '/dashboard?goal_id=' + goalId);
      const board = JSON.parse(boardText) as ESObject;
      this.coach = readField(board, 'coach_message');
      const rawTasks = board['today_tasks'] as Array<ESObject>;
      const next: TaskItem[] = [];
      if (rawTasks) {
        for (let i = 0; i < rawTasks.length; i++) {
          const item = rawTasks[i];
          next.push({
            id: readField(item, 'id'),
            title: readField(item, 'title'),
            minutes: readField(item, 'duration_min'),
            status: readField(item, 'status'),
            reason: readField(item, 'reason')
          });
        }
      }
      this.tasks = next;
      this.hint = '';
    } catch (err) {
      this.hint = (err as Error).message;
    }
  }

  async finish(task: TaskItem): Promise<void> {
    if (!this.client || task.status === 'done') {
      return;
    }
    try {
      await this.client.request(
        http.RequestMethod.PATCH,
        '/goals/tasks/' + task.id,
        JSON.stringify({ status: 'done' })
      );
      await this.reload();
    } catch (err) {
      this.hint = (err as Error).message;
    }
  }

  build() {
    Column() {
      Scroll() {
        Column() {
          Text('今日')
            .fontSize(28)
            .fontWeight(FontWeight.Bold)
          Text(this.examName)
            .fontSize(14)
            .fontColor('#5C564C')
            .margin({ top: 6, bottom: 12 })
          Text(this.coach)
            .fontSize(15)
            .lineHeight(22)
            .margin({ bottom: 16 })
          if (this.tasks.length === 0) {
            Text('今天还没有任务。可以在网页端生成计划后再回来看。')
              .fontSize(14)
              .fontColor('#5C564C')
          }
          ForEach(this.tasks, (task: TaskItem) => {
            Column() {
              Text(task.title)
                .fontSize(16)
                .fontWeight(FontWeight.Medium)
              Text(task.minutes + ' 分钟 · ' + (task.status === 'done' ? '已完成' : '待完成'))
                .fontSize(12)
                .fontColor('#5C564C')
                .margin({ top: 4 })
              if (task.reason.length > 0) {
                Text(task.reason)
                  .fontSize(13)
                  .margin({ top: 6 })
              }
              if (task.status !== 'done') {
                Button('完成')
                  .margin({ top: 8 })
                  .backgroundColor('#1F6B4A')
                  .onClick(() => {
                    this.finish(task);
                  })
              }
            }
            .width('100%')
            .padding(14)
            .margin({ bottom: 10 })
            .backgroundColor('#FFFFFF')
            .borderRadius(12)
            .alignItems(HorizontalAlign.Start)
          }, (task: TaskItem) => task.id)
          if (this.hint.length > 0) {
            Text(this.hint).fontSize(13).fontColor('#8A3B2C').margin({ top: 8 })
          }
          Button('刷新')
            .margin({ top: 8 })
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
      .align(Alignment.TopStart)

      AppNav({ current: 'today' })
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#F6F3EC')
  }
}
