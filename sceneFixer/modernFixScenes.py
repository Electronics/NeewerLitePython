import os
import ruamel.yaml
from requests import post

# defaultTransition = 10
# panelTransition = 15

overwriteFile = False
homeassistantIP = "10.71.11.107"

finished = True

print("Getting scenes.yaml from home assistant")
os.system("scp -i id_rsa hassio@"+homeassistantIP+":/root/config/scenes.yaml .")

yaml = ruamel.yaml.YAML(typ="rt")
yaml.preserve_quotes = True
with open("scenes.yaml", "r") as f:
	try:
		scenes = yaml.load(f)
		print("Loaded yaml file")
		for scene in scenes:
			if "entities" in scene.keys():
				for entityName, entity in scene["entities"].items():
					if "effect" in entity.keys() and entity["effect"]=="None":
						print(f"{scene['name']}.{entityName}: removing 'effect: None'")
						del entity["effect"]
					if "state" in entity.keys() and entity["state"] == "off":
						entity["state"] = ruamel.yaml.scalarstring.SingleQuotedScalarString("on")
						entity["brightness"] = 0
						print(f"{scene['name']}.{entityName}: changing state=off to brightness=0")
					# if "light.panel" in entityName:
					# 	entity["transition"] = panelTransition
					# else:
					# 	entity["transition"] = defaultTransition
		finished = True

	except ruamel.yaml.YAMLError as exc:
		print(exc)

# original file is now closed
if finished:
	print("Saving file")
	with open("scenes.yaml" if overwriteFile else "scenesOut.yaml", "w") as file:
		yaml.dump(scenes, file)
	print("Sending scenes.yaml back to home assistant")
	os.system("scp -i id_rsa scenesOut.yaml hassio@" + homeassistantIP + ":/tmp/")
	os.system("ssh -i id_rsa hassio@" + homeassistantIP + " sudo mv /tmp/scenesOut.yaml /root/config/scenes.yaml")

	url = "http://"+homeassistantIP+":8123/api/services/scene/Reload"
	headers = {
		"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI0ZTc1OGM1YTJlYTY0MjdmOTdjZTIzMmZkZTljNmM2YSIsImlhdCI6MTY5ODUzNDkxNCwiZXhwIjoyMDEzODk0OTE0fQ.y7SSQv3CtWkFlhXUWJeeLhQ4wF6D200bzidWB8kcWhk",
		"content-type": "application/json",
	}
	print("Reloading home assistant scenes")
	response = post(url, headers=headers)
	print(response.text)

print("Press any key to exit")
input()
