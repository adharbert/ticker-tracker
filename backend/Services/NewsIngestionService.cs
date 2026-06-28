namespace NewsMarketAgent.Api.Services;

public interface INewsIngestionService
{
    Task<string> IngestLatestAsync();
}

public class NewsIngestionService(IHttpClientFactory http, ILogger<NewsIngestionService> log) : INewsIngestionService
{
    public async Task<string> IngestLatestAsync()
    {
        var client = http.CreateClient("python-agent");
        try
        {
            var resp = await client.PostAsync("/trigger", null);
            if (resp.IsSuccessStatusCode)
            {
                log.LogInformation("Ingest triggered on Python agent");
                return "triggered";
            }
            log.LogWarning("Python agent returned {Status}", resp.StatusCode);
            return "python_agent_error";
        }
        catch (HttpRequestException ex)
        {
            log.LogError(ex, "Could not reach Python agent at {Base}", client.BaseAddress);
            return "python_agent_unreachable";
        }
    }
}
