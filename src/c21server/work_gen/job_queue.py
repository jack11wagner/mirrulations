import json


class JobQueue:

    def __init__(self, database):
        self.database = database

    def add_job(self, url):
        job_id = self.get_job_id()
        job = {'job_id': job_id,
               'url': url}
        self.database.lpush('jobs_waiting_queue', json.dumps(job))

    def get_num_jobs(self):
        return self.database.llen('jobs_waiting_queue')

    def get_job(self):
        return json.loads(self.database.lpop('jobs_waiting_queue'))

    def get_job_id(self):
        job_id = self.database.incr('last_job_id')
        return job_id
