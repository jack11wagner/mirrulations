# pylint: disable=too-many-locals
import time
import os
import sys
from json import dumps, loads
import requests
from dotenv import load_dotenv
from mirrclient.saver import Saver
from mirrclient.disk_saver import DiskSaver
from mirrclient.s3_saver import S3Saver
from mirrcore.path_generator import PathGenerator


class NoJobsAvailableException(Exception):
    """
    Raises an Exception when there are no jobs available in the workserver.
    """

    def __init__(self, message="There are no jobs available"):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f'{self.message}'


def is_environment_variables_present():
    """
    A boolean function that returns whether environment variables are
    present for performing jobs.

    Returns
    -------
    Boolean
    """
    return (os.getenv('WORK_SERVER_HOSTNAME') is not None
            and os.getenv('WORK_SERVER_PORT') is not None
            and os.getenv('API_KEY') is not None
            and os.getenv('ID') is not None)


class Client:
    """
    The Client class performs jobs given to it by a workserver
    It receives a job, performs it depending on the job type.
    A job is performed by calling an api endpoint to request
    a json object. The Client sends back the results back
    to the workserver.

    Attributes
    ----------
    api_key : str
        Api key used to authenticate requests made to api
    server_validator : ServerValidator
        This is used to validate requests made between the
        workserver and the Client
    client_id : int
        An id that defaults to -1 but is eventually replaced by a
        value from the workserver.
    """

    def __init__(self):
        self.api_key = os.getenv('API_KEY')
        self.client_id = os.getenv('ID')
        self.path_generator = PathGenerator()
        self.saver = Saver(savers=[DiskSaver(),
                                   S3Saver(bucket_name="mirrulations")])
        self.bucket_name = "mirrulations"

        hostname = os.getenv('WORK_SERVER_HOSTNAME')
        port = os.getenv('WORK_SERVER_PORT')
        self.url = f'http://{hostname}:{port}'

    def get_job(self):
        """
        Get a job from the work server.
        Converts API URL to regulations.gov URL and prints to logs.
        From: https://api.regulations.gov/v4/dockets/type_id
        To: https://www.regulations.gov/docket/type_id

        :raises: NoJobsAvailableException
            If no job is available from the work server
        """

        response = requests.get(f'{self.url}/get_job',
                                params={'client_id': self.client_id},
                                timeout=10)

        job = loads(response.text)
        link = 'https://www.regulations.gov/'
        if 'error' in job:
            raise NoJobsAvailableException()
        split_url = str(job['url']).split('/')
        job_type = split_url[-2][:-1]  # Removes plural from job type
        type_id = split_url[-1]
        print(f'Regulations.gov link: {link}{job_type}/{type_id}')
        print(f'API URL: {job["url"]}')
        return job

    def send_job(self, job, job_result):
        """
        Returns the job results to the workserver
        If there are any errors in the job_result, the data json is returned
        as  {'job_id': job_id, 'results': job_result}
        else {
            'job_id': job_id, 'results': job_result,
            'directory': output_path
            }

        Parameters
        ----------
        job_id : str
            id for current job
        job_result : dict
            results from a performed job
        """
        data = {
            'job_type': job['job_type'],
            'job_id': job['job_id'],
            'results': job_result,
            # Updated to get reg_id and agency from regulations json
            # - Jack W. 3/14
            'reg_id': job['reg_id'],
            'agency': job['agency']
        }
        print(f'Sending Job {job["job_id"]} to Work Server')
        if 'error' not in job_result:
            data['directory'] = self.path_generator.get_path(job_result)

        self._put_results(data)
        self.put_results_to_mongo(data)
        comment_has_attachment = self.does_comment_have_attachment(job_result)

        if data["job_type"] == "comments" and comment_has_attachment:
            self.download_all_attachments_from_comment(data, job_result)
        # For now, still need to send original put request for Mongo
        # requests.put(
        #     f'{self.url}/_put_results',
        #     json=dumps(data['job_id']),
        #     params={'client_id': self.client_id},
        #     timeout=10
        # )

    def _put_results(self, data):
        """
        Ensures data format matches expected format
        If results are valid, writes them to disk

        Parameters
        ----------
        data : dict
            the results from a performed job
        """
        if any(x in data['results'] for x in ['error', 'errors']):
            print(f"{data['job_id']}: Errors found in results")
            return
        dir_, filename = data['directory'].rsplit('/', 1)
        # self.saver.make_path(dir_)
        self.saver.save_json(f'/data{dir_}/{filename}', data)
        # self.saver.save_json_to_s3(bucket=self.bucket_name,
        #                            path=f'data{dir_}/{filename}',
        #                            data=data)
        print(f"{data['job_id']}: Results written to disk")

    def perform_job(self, job_url):
        """
        Performs job via get_request function by giving it the job_url combined
        with the Client api_key for validation.

        Parameters
        ----------
        job_url : str
            url from a job

        Returns
        -------
        dict
            json results of the performed job
        """
        print('Performing job')
        try:
            if "?" in job_url:
                return requests.get(job_url + f'&api_key={self.api_key}',
                                    timeout=10).json()
            return requests.get(job_url + f'?api_key={self.api_key}',
                                timeout=10).json()
        except requests.exceptions.ReadTimeout:
            return {"error": "Read Timeout"}

    def download_all_attachments_from_comment(self, data, comment_json):
        '''
        Downloads all attachments for a comment

        Parameters
        ----------
        data : dict
            Dictionary of the job
            Keys include: 'job_type', 'job_id', 'results', 'reg_id', 'agency'

        comment_json : dict
            The json of the comment

        '''

        path_list = self.path_generator.get_attachment_json_paths(comment_json)
        counter = 0
        comment_id_str = f"Comment - {comment_json['data']['id']}"
        print(f"Found {len(path_list)} attachment(s) for {comment_id_str}")
        for included in comment_json["included"]:
            attributes = included["attributes"]
            if (attributes["fileFormats"] and
                    attributes["fileFormats"] not in ["null", None]):
                for attachment in included['attributes']['fileFormats']:
                    url = attachment['fileUrl']
                    self.download_single_attachment(url, path_list[counter],
                                                    data)
                    print(f"Downloaded {counter+1}/{len(path_list)} "
                          f"attachment(s) for {comment_id_str}")
                    counter += 1

    def download_single_attachment(self, url, path, data):
        '''
        Downloads a single attachment for a comment and
        writes it to its correct path
        Also puts the attachment 'data' dict to the work server for mongo entry

        Parameters
        ----------
        url : str
            The attachment download url
            Ex: http://downloads.regulations.gov/####

        path : str
            The attachment path the download should be written to
            Comes from the path_generator.get_attachment_json_paths

        data : dict
            Dictionary of the job
            Keys include: 'job_type', 'job_id', 'results', 'reg_id', 'agency'

        '''
        response = requests.get(url, timeout=10)
        dir_, filename = path.rsplit('/', 1)
        # make_path should be called by the DiskSaver save_binary function
        # self.saver.make_path(dir_)
        self.saver.save_binary(f'/data{dir_}/{filename}', response.content)
        # S3 path needs to start with data, disk path needs to start with /data
        # self.saver.save_binary_to_s3(bucket=self.bucket_name,
        #                              path=f'data{dir_}/{filename}',
        #                              data=response.content)

        print(f"SAVED attachment - {url} to path: ", path)
        filename = path.split('/')[-1]
        data = self.add_attachment_information_to_data(data, path, filename)
        self.put_results_to_mongo(data)

    def add_attachment_information_to_data(self, data, path, filename):
        data['job_type'] = 'attachments'
        data['attachment_path'] = f'/data/data{path}'
        data['attachment_filename'] = filename
        return data

    def put_results_to_mongo(self, data):
        requests.put(f'{self.url}/put_results', json=dumps(data),
                     params={'client_id': self.client_id},
                     timeout=10)

    def does_comment_have_attachment(self, comment_json):
        """
        Validates whether a json for a comment has any
        attachments to be downloaded.

        RETURNS
        -------
        True or False depending if there is an attachment
        available to download from a comment
        """
        if "included" in comment_json and len(comment_json["included"]) > 0:
            return True
        return False

    def job_operation(self):
        """
        Processes a job.
        The Client gets the job from the workserver, performs the job
        based on job_type, then sends back the job results to
        the workserver.
        """
        print('Processing job from work server')
        job = self.get_job()
        result = self.perform_job(job['url'])
        self.send_job(job, result)
        if any(x in result for x in ('error', 'errors')):
            print(f'FAILURE: Error in {job["url"]}\nError: {result["error"]}')
        else:
            print(f'SUCCESS: {job["url"]} complete')


if __name__ == '__main__':
    load_dotenv()
    if not is_environment_variables_present():
        print('Need client environment variables')
        sys.exit(1)

    client = Client()

    while True:
        try:
            client.job_operation()
        except NoJobsAvailableException:
            print("No Jobs Available")
        time.sleep(3.6)
