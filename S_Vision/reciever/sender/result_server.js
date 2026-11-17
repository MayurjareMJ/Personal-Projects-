// const express = require("express");
// const { Queue } = require("bullmq");

// const app = express();

// app.use(express.json());

// const queue = new Queue(
//     "survelliance.fire-smoke-queue",
//     {
//         connection: {
//             host: "localhost",
//             port: 6379
//         }
//     }
// );
// app.post(
//     "/result",
//     async (req, res) => {

//         try {

//             await queue.add(
//                 "fire-smoke-job",
//                 req.body
//             );

//             console.log(
//                 "RESULT QUEUED",
//                 req.body.camera_id
//             );

//             res.sendStatus(200);

//         }
//         catch(err){

//             console.error(err);

//             res.sendStatus(500);
//         }
//     }
// );

// app.listen(
//     3001,
//     () => {

//         console.log(
//             "Result Server Started"
//         );
//     }
// );

const express = require("express");
const { Queue } = require("bullmq");

const app = express();

app.use(express.json());

const queue = new Queue("survelliance.fire-smoke-queue", {
  connection: {
    host: "localhost",
    port: 6379,
  },
});

app.post("/result", async (req, res) => {
  try {
    await queue.add("fire-smoke-job", req.body, {
      removeOnComplete: {
        count: 100,
      },
      removeOnFail: {
        count: 100,
      },
    });

    console.log("RESULT QUEUED", req.body.camera_id);

    res.sendStatus(200);
  } catch (err) {
    console.error(err);

    res.sendStatus(500);
  }
});

app.listen(3001, () => {
  console.log("Result Server Started");
});
