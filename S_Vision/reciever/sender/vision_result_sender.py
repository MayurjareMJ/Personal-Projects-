# import requests


# class BULLMQ_SENDER:

#     def __init__(self):

#         self.url = "http://localhost:3001/result"

#     def send(
#         self,
#         use_case,
#         key,
#         message_dict
#     ):
#         print("BEFORE SEND")
#         print(message_dict)

#         payload = message_dict

#         try:

#             response = requests.post(
#                 self.url,
#                 json=payload,
#                 timeout=5
#             )

#             print(
#                 f"[INFO] Result queued | "
#                 f"status={response.status_code}"
#             )

#         except Exception as e:

#             print(
#                 f"[ERROR] Failed sending result: {e}"
#             )





















import requests


class BULLMQ_SENDER:

    def __init__(self):

        self.url = "http://localhost:3001/result"
        self.session = requests.Session()

    def send(
        self,
        use_case,
        key,
        message_dict
    ):


        payload = message_dict

        try:

            response = self.session.post(
                self.url,
                json=payload,
                timeout=(2, 5)
            )

            print(
                f"[INFO] Result queued | "
                f"status={response.status_code}"
            )

        except Exception as e:

            print(
                f"[ERROR] Failed sending result: {e}"
            )