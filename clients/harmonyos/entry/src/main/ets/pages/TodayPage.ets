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
  @State streak: string = '0';
  @State dueCards: string = '0';
  @State daysLeft: string = '';
  @State nextStep: string = '';
  @State loopText: string = '';
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
      this.daysLeft = readField(goal, 'days_left');
      const boardText = await this.client.request(http.RequestMethod.GET, '/dashboard?goal_id=' + goalId);
      const board = JSON.parse(boardText) as ESObject;
      this.coach = readField(board, 'coach_message');
      this.streak = readField(board, 'streak') || '0';
      this.nextStep = readField(board, 'next_step');
      const steps = board['loop_steps'] as Array<ESObject>;
      const labels: string[] = [];
      if (steps) {
        for (let i = 0; i < steps.length; i++) {
          const done = steps[i]['done'];
          labels.push(readField(steps[i], 'label') + (done === true ? '已完成' : '未完成'));
        }
      }
      this.loopText = labels.join(' · ');
      try {
        const deckText = await this.client.request(http.RequestMethod.GET, '/goals/' + goalId + '/flashcards');
        const deck = JSON.parse(deckText) as ESObject;
        this.dueCards = readField(deck, 'due_count') || '0';
      } catch (cardErr) {
        this.dueCards = '0';
      }
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
          Text(this.examName + (this.daysLeft.length > 0 ? ' · 还剩 ' + this.daysLeft + ' 天' : ''))
            .fontSize(14)
            .fontColor('#5C564C')
            .margin({ top: 6 })
          Text('已连续学习 ' + this.streak + ' 天 · 待复习闪卡 ' + this.dueCards + ' 张')
            .fontSize(14)
            .margin({ top: 6, bottom: 12 })
          Text(this.nextStep)
            .fontSize(15)
            .fontWeight(FontWeight.Medium)
            .margin({ bottom: 6 })
          if (this.loopText.length > 0) {
            Text(this.loopText)
              .fontSize(13)
              .fontColor('#5C564C')
              .margin({ bottom: 8 })
          }
          Text('今日重点')
            .fontSize(13)
            .fontColor('#5C564C')
          Text(this.coach)
            .fontSize(15)
            .lineHeight(22)
            .margin({ bottom: 8 })
          Text('建议顺序：完成下面的任务，再去拍题或口语，最后看复盘。随堂测可在网页端对着本节知识点进行。')
            .fontSize(13)
            .fontColor('#5C564C')
            .margin({ bottom: 12 })
          Row({ space: 8 }) {
            Button('拍题')
              .layoutWeight(1)
              .backgroundColor('#1F6B4A')
              .onClick(() => {
                router.replaceUrl({ url: 'pages/CapturePage' });
              })
            Button('口语')
              .layoutWeight(1)
              .backgroundColor('#1F6B4A')
              .onClick(() => {
                router.replaceUrl({ url: 'pages/CoachPage' });
              })
            Button('复盘')
              .layoutWeight(1)
              .backgroundColor('#E7E1D6')
              .fontColor('#1C1915')
              .onClick(() => {
                router.replaceUrl({ url: 'pages/ReviewPage' });
              })
          }
          .width('100%')
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
