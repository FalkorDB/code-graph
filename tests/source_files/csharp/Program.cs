using System;

namespace TestProject
{
    public interface ILogger
    {
        void Log(string message);
    }

    public class ConsoleLogger : ILogger
    {
        public void Log(string message)
        {
            Console.WriteLine(message);
        }
    }

    /// <summary>
    /// Represents a task to be executed.
    /// </summary>
    public class Task
    {
        public string Name { get; set; }
        public int Duration { get; set; }

        private ILogger _logger;

        public Task(string name, int duration, ILogger logger)
        {
            Name = name;
            Duration = duration;
            _logger = logger;
            _logger.Log("Task created: " + name);
        }

        public bool Execute()
        {
            _logger.Log("Executing: " + Name);
            return true;
        }

        public void Abort(float delay)
        {
            _logger.Log("Aborting: " + Name);
            Execute();
        }
    }
}
