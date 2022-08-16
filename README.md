# Discord-bot
Discord bot developed for students of Murmansk secondary school №36.

----
## Setup
Just add bot to your server ([click](https://discord.com/api/oauth2/authorize?client_id=681930216221704243&permissions=8&scope=bot))

There is also a ready-made server template for students of the same class, which we have been using for two years ([click](https://discord.new/QwNU7gNJfFWz))

____
## About modules

### School
Functionality for students

Features:
- Schedule with student class selection distribution (daily or one-time)
- Homework received from the server distribution (daily and weekly)

For automatic distribution, you must enter all the data using the following commands: -set_course, -set_lesson, -set_timetable. 
Then You need to turn distribution on with -toggle_schedule.
For more information you can use -help [command_name] command.

### English
Helps to learn a set of english words or phrases

Features:
- Create your own word list in Google Sheets
- Learn written words or phrases using simple test system (two types of testing)

### Admission
Simplifies the analysis of the competitive situation in 3 universities (special module).

Features:
- Parser of competitive lists of the ITMO (Paid education)
- Parser of competitive lists of the SPbETU (Budget education)
- Parser of competitive lists of the SPbU (Budget education)
- Filling a Google Sheets table with collected data

### Admin
Provides basic server administration functionality

Features:
- Ban a member from a server
- Kick a member from the server
- Mute a member in the server
- Clear channel's messages (with amount of messages and author filters)
- Check bot health (ping)

### Settings
Configure bot functionality

Features:
- Turn on/off notification system  for member join/remove in the system channel
- Some hidden features (for developers)

----
My first project. With it, I took 4th place in the research competition "Start to Innovate" of the Moscow Institute of Physics and Technology
