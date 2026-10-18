using System.Diagnostics;
using System.Reflection;

[assembly: AssemblyTitle("문장읽기 웹")]
[assembly: AssemblyProduct("문장읽기")]

/// 작업 표시줄 버튼. 누르면 문장읽기 웹을 기본 브라우저로 연다.
internal static class SentenceReadingWeb {
    private const string Url = "https://asr-sentence-reading-984608876300.asia-northeast3.run.app/app/";

    private static void Main() {
        Process.Start(new ProcessStartInfo {
            FileName = Url,
            UseShellExecute = true,
        });
    }
}
