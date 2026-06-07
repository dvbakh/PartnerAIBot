from models.task import Task
from storage.collector_repository import CollectorRepository
from config import GEO_STRUCTURE


class Coordinator:

    def __init__(self, task: Task):
        self.task = task

    def create_collectors(self):

        created_collectors = []

        for geo in self.task.geo_list:

            if geo not in GEO_STRUCTURE:
                continue

            geo_info = GEO_STRUCTURE[geo]

            for respondent in geo_info["respondents"]:

                collector_id = CollectorRepository.create(
                    task_id=self.task.id,
                    geo=geo,
                    channel=respondent["channel"],
                    respondent_chat_id=respondent["chat_id"],
                    status="created"
                )

                created_collectors.append(
                    {
                        "collector_id": collector_id,
                        "geo": geo,
                        "channel": respondent["channel"]
                    }
                )

        return created_collectors

    async def start_collection(self, bot):

        collectors = CollectorRepository.get_by_task(
            self.task.id
        )

        for collector in collectors:

            text = (
                f"Здравствуйте.\n\n"
                f"Необходимо предоставить бюджеты за "
                f"{self.task.month}.\n\n"
                f"GEO: {collector['geo']}\n"
                f"Канал: {collector['channel']}\n\n"
                f"Дедлайн: {self.task.deadline}\n\n"
                f"Пришлите список партнеров и бюджетов."
            )

            await bot.send_message(
                chat_id=collector["respondent_chat_id"],
                text=text
            )

            CollectorRepository.update_status(
                collector["id"],
                "waiting_response"  # вместо "contacted"
            )