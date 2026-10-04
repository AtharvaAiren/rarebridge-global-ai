require 'json'
require 'yaml'
require 'date'

data = File.join(__dir__, 'data')
entries = Dir[File.join(data, 'raw', '*.yaml')].sort.map do |path|
  {
    'source_file' => File.basename(path),
    'record' => YAML.safe_load(File.read(path), permitted_classes: [Date], aliases: false)
  }
end
File.write(File.join(data, 'disorders.json'), JSON.pretty_generate(entries) + "\n")
puts "Converted #{entries.length} pinned disease records; no claims were verified."
