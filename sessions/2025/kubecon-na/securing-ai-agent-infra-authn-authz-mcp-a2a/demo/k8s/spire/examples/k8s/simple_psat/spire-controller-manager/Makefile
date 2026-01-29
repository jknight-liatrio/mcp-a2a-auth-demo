.PHONY: template clean

helm-chart.yaml: helmfile.yaml spire-values.yaml
	helmfile repos
	helmfile template > helm-chart.yaml